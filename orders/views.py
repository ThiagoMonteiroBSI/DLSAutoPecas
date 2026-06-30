from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated, AllowAny

from .models import Order
from .serializers import OrderSerializer, ShippingSimulationSerializer
from catalog.models import Product # Importação necessária para ler os pesos

class CheckoutView(generics.CreateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    # Recomenda-se adicionar permission_classes se não for uma compra como convidado
    # permission_classes = [IsAuthenticated]

class OrderListView(generics.ListAPIView):
    queryset = Order.objects.all().order_by('-created_at')
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

class ShippingSimulationView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ShippingSimulationSerializer(data=request.data)
        
        if serializer.is_valid():
            zip_code = serializer.validated_data.get('zip_code')
            items = serializer.validated_data.get('items', [])
            
            # Cálculo dinâmico do peso total do carrinho
            total_weight_kg = 0.0
            
            for item in items:
                try:
                    product = Product.objects.get(id=item.get('product_id'))
                    # Presume-se que existe um campo weight_kg. Default 1.0 se não existir
                    weight = getattr(product, 'weight_kg', 1.0)
                    quantity = item.get('quantity', 1)
                    total_weight_kg += float(weight) * int(quantity)
                except Product.DoesNotExist:
                    continue
            
            # Lógica mockada reativa: o preço e prazo mudam conforme o peso
            base_price = 15.00
            weight_tax = total_weight_kg * 3.50 # R$3,50 por KG

            mock_shipping_options = [
                {
                    "service": "PAC (Correios)", 
                    "price": round(base_price + weight_tax, 2), 
                    "deadline_days": 7
                },
                {
                    "service": "SEDEX (Correios)", 
                    "price": round((base_price + weight_tax) * 2.2, 2), 
                    "deadline_days": 3
                },
                {
                    "service": "Jadlog Package", 
                    "price": round((base_price + weight_tax) * 1.4, 2), 
                    "deadline_days": 5
                }
            ]
            
            return Response(mock_shipping_options, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PaymentWebhookView(APIView):
    """
    Webhook para recebimento de atualizações de pagamento.
    IMPORTANTE: Em produção, verifique o cabeçalho 'x-webhook-signature' 
    para garantir que a requisição veio realmente do gateway de pagamento.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        payload = request.data

        order_id = payload.get('reference_id') 
        payment_status = payload.get('status') 

        # Blindagem 1: Payload incompleto
        if not order_id or not payment_status:
            return Response({"error": "Payload inválido. Faltam parâmetros obrigatórios."}, status=status.HTTP_400_BAD_REQUEST)

        # Blindagem 2: Tratamento de exceção para pedidos inexistentes
        try:
            order = Order.objects.get(id=order_id)

            status_upper = str(payment_status).upper()
            if status_upper in ['CONFIRMED', 'RECEIVED', 'PAID']:
                order.status = 'PAID'
            elif status_upper in ['REFUNDED', 'CANCELED']:
                order.status = 'CANCELED'
            
            order.save()
            return Response({"message": "Webhook recebido e processado com sucesso."}, status=status.HTTP_200_OK)

        except Order.DoesNotExist:
            return Response({"error": f"Pedido referenciado ({order_id}) não encontrado no banco de dados."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            # Fallback seguro para não travar gateways que realizam retries se receberem erro 500 sem tratamento
            return Response({"error": "Erro interno ao processar o webhook."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)