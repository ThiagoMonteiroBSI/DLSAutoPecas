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

import hashlib
import requests
import xml.etree.ElementTree as ET
from decimal import Decimal

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.core.cache import cache

from .models import Order
from .serializers import OrderSerializer, ShippingSimulationSerializer
from catalog.models import Product # Importação necessária para ler pesos e dimensões

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

        # Peso mínimo tarifado pelos Correios
        if total_weight < Decimal('0.3'):
            total_weight = Decimal('0.3')

        # 2. Cubagem: transforma o volume total numa "caixa cúbica equivalente"
        cubic_side = float(total_volume) ** (1 / 3) if total_volume > 0 else 16.0

        final_length = max(16.0, cubic_side)
        final_width = max(11.0, cubic_side)
        final_height = max(2.0, cubic_side)

        if (final_length + final_width + final_height) > 200:
            return Response(
                {'error': 'Dimensões totais do pedido excedem o limite dos Correios.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3. Cache (1 hora) para o mesmo par origem/destino/peso/volume
        cache_str = f"{self.ORIGIN_CEP}_{destination_cep}_{total_weight:.2f}_{total_volume:.2f}"
        cache_key = "frete_" + hashlib.md5(cache_str.encode()).hexdigest()

        cached_result = cache.get(cache_key)
        if cached_result:
            return Response(cached_result, status=status.HTTP_200_OK)

        # 4. Chamada aos Correios (serviços sem contrato)
        # 04510 = PAC | 04014 = SEDEX
        services = {'PAC (Correios)': '04510', 'SEDEX (Correios)': '04014'}
        results = []

        try:
            for name, code in services.items():
                url = "http://ws.correios.com.br/calculador/CalcPrecoPrazo.aspx"
                params = {
                    'nCdEmpresa': '', 'sDsSenha': '',
                    'sCepOrigem': self.ORIGIN_CEP,
                    'sCepDestino': destination_cep,
                    'nVlPeso': str(total_weight),
                    'nCdFormato': '1',
                    'nVlComprimento': str(int(final_length)),
                    'nVlAltura': str(int(final_height)),
                    'nVlLargura': str(int(final_width)),
                    'sCdMaoPropria': 'N',
                    'nVlValorDeclarado': '0',
                    'sCdAvisoRecebimento': 'N',
                    'nCdServico': code,
                    'nVlDiametro': '0',
                    'StrRetorno': 'xml',
                    'nIndicaCalculo': '3'
                }

                response = requests.get(url, params=params, timeout=5)
                root = ET.fromstring(response.content)
                c_servico = root.find('cServico')

                erro = c_servico.find('Erro').text
                msg_erro = c_servico.find('MsgErro').text

                if erro in ('0', '011'):  # 0 = OK, 011 = OK com aviso
                    valor = c_servico.find('Valor').text
                    prazo = c_servico.find('PrazoEntrega').text

                    results.append({
                        'service': name,
                        'price': float(valor.replace('.', '').replace(',', '.')) if ',' in valor else float(valor),
                        'deadline_days': int(prazo),
                        'warning': msg_erro if erro == '011' else None
                    })

            if not results:
                return Response(
                    {'error': 'Correios não atendem este CEP para as dimensões enviadas.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            cache.set(cache_key, results, 3600)
            return Response(results, status=status.HTTP_200_OK)

        except requests.exceptions.RequestException:
            return Response(
                {'error': 'Serviço dos Correios indisponível no momento. Tente novamente mais tarde.'},
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