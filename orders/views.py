import hashlib
import requests
from decimal import Decimal

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.core.cache import cache
from django.conf import settings

from .models import Order
from .serializers import OrderSerializer, ShippingSimulationSerializer
from catalog.models import Product  # Importação necessária para ler pesos e dimensões


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
    # CEP da Loja/Depósito de origem (apenas números)
    ORIGIN_CEP = "89200000"

    permission_classes = [AllowAny]

    def post(self, request):
        # Proteção: verifica se o token do Melhor Envio foi configurado
        if not getattr(settings, 'MELHOR_ENVIO_TOKEN', None):
            return Response(
                {'error': 'Token do Melhor Envio não configurado no backend.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        serializer = ShippingSimulationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        zip_code = serializer.validated_data.get('zip_code')
        items = serializer.validated_data.get('items', [])

        destination_cep = str(zip_code).replace('-', '').strip()
        if len(destination_cep) != 8 or not destination_cep.isdigit():
            return Response({'error': 'CEP de destino inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        if not items:
            return Response({'error': 'Carrinho vazio.'}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Obter produtos e somar peso/volume total do carrinho
        total_weight = Decimal('0.0')
        total_volume = Decimal('0.0')

        for item in items:
            try:
                product = Product.objects.get(id=item.get('product_id'))
            except Product.DoesNotExist:
                return Response(
                    {'error': f"Produto {item.get('product_id')} não encontrado."},
                    status=status.HTTP_404_NOT_FOUND
                )

            quantity = int(item.get('quantity', 1))

            # getattr com defaults: funciona mesmo antes de rodar a migration
            # que adiciona length_cm/width_cm/height_cm ao model Product
            weight = Decimal(str(getattr(product, 'weight_kg', 1.0) or 1.0))
            length = Decimal(str(getattr(product, 'length_cm', 16) or 16))
            width = Decimal(str(getattr(product, 'width_cm', 11) or 11))
            height = Decimal(str(getattr(product, 'height_cm', 2) or 2))

            total_weight += weight * quantity
            total_volume += (length * width * height) * quantity

        # Peso mínimo tarifado
        if total_weight < Decimal('0.3'):
            total_weight = Decimal('0.3')

        # 2. Cubagem: transforma o volume total numa "caixa cúbica equivalente"
        cubic_side = float(total_volume) ** (1 / 3) if total_volume > 0 else 16.0

        final_length = max(16.0, cubic_side)
        final_width = max(11.0, cubic_side)
        final_height = max(2.0, cubic_side)

        if (final_length + final_width + final_height) > 200:
            return Response(
                {'error': 'Dimensões totais do pedido excedem o limite das transportadoras.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3. Cache (1 hora) para o mesmo par origem/destino/peso/volume
        cache_str = f"{self.ORIGIN_CEP}_{destination_cep}_{total_weight:.2f}_{total_volume:.2f}"
        cache_key = "frete_me_" + hashlib.md5(cache_str.encode()).hexdigest()

        cached_result = cache.get(cache_key)
        if cached_result:
            return Response(cached_result, status=status.HTTP_200_OK)

        # 4. Requisição para o Melhor Envio
        url = f"{settings.MELHOR_ENVIO_URL.rstrip('/')}/api/v2/me/shipment/calculate"
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {settings.MELHOR_ENVIO_TOKEN}",
            'User-Agent': 'DLS_AutoPecas_API (contato@dlsautopecas.com.br)'  # ajuste o e-mail de contato
        }

        payload = {
            "from": {"postal_code": self.ORIGIN_CEP},
            "to": {"postal_code": destination_cep},
            "volumes": [
                {
                    "weight": float(total_weight),
                    "width": int(final_width),
                    "height": int(final_height),
                    "length": int(final_length)
                }
            ]
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)

            if response.status_code == 401:
                return Response(
                    {'error': 'Token de integração inválido ou expirado.'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            if response.status_code == 429:
                return Response(
                    {'error': 'Limite de cotações atingido. Tente novamente em um minuto.'},
                    status=status.HTTP_429_TOO_MANY_REQUESTS
                )

            response.raise_for_status()

            me_options = response.json()
            results = []

            for opt in me_options:
                # Se a transportadora não atender (ex: peso excedido), a chave "error" vem preenchida
                if opt.get('error'):
                    continue

                company_name = opt.get('company', {}).get('name', 'Transportadora')
                service_name = opt.get('name', '')
                display_name = f"{company_name} {service_name}".strip()

                price_value = opt.get('custom_price') or opt.get('price')
                deadline = opt.get('custom_delivery_time') or opt.get('delivery_time')

                results.append({
                    'service': display_name,
                    # Mantido como número (não string) para compatibilidade com
                    # Intl.NumberFormat no FreteCalculator.vue
                    'price': round(float(price_value), 2),
                    # Chave "deadline_days" mantida igual ao contrato já usado
                    # pelo FreteCalculator.vue e CartView.vue
                    'deadline_days': int(deadline),
                    'warning': None
                })

            if not results:
                return Response(
                    {'error': 'Nenhuma transportadora atende este CEP para as dimensões enviadas.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            cache.set(cache_key, results, 3600)
            return Response(results, status=status.HTTP_200_OK)

        except requests.exceptions.Timeout:
            return Response(
                {'error': 'A integração de fretes demorou a responder. Tente novamente.'},
                status=status.HTTP_504_GATEWAY_TIMEOUT
            )
        except requests.exceptions.RequestException:
            return Response(
                {'error': 'Serviço de cotação indisponível no momento. Tente novamente mais tarde.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )


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
            return Response(
                {"error": "Payload inválido. Faltam parâmetros obrigatórios."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Blindagem 2: Tratamento de exceção para pedidos inexistentes
        try:
            order = Order.objects.get(id=order_id)

            status_upper = str(payment_status).upper()
            if status_upper in ['CONFIRMED', 'RECEIVED', 'PAID']:
                order.status = 'PAID'
            elif status_upper in ['REFUNDED', 'CANCELED']:
                order.status = 'CANCELED'

            order.save()
            return Response(
                {"message": "Webhook recebido e processado com sucesso."},
                status=status.HTTP_200_OK
            )

        except Order.DoesNotExist:
            return Response(
                {"error": f"Pedido referenciado ({order_id}) não encontrado no banco de dados."},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception:
            # Fallback seguro para não travar gateways que fazem retry em erro 500 sem tratamento
            return Response(
                {"error": "Erro interno ao processar o webhook."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )