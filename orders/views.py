import os
import hashlib

import requests
from django.conf import settings
from django.core.cache import cache
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated, AllowAny

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
    """
    Simulação de frete usando a API de Cálculo de Fretes do Melhor Envio
    (cotação "por produtos" — o próprio Melhor Envio calcula o empacotamento
    e retorna as cotações de todas as transportadoras habilitadas na conta).
    Docs: https://docs.melhorenvio.com.br/reference/calculo-de-fretes-por-produtos
    """
    permission_classes = [AllowAny]

    ORIGIN_CEP = "89200000"

    # Produção. Só troque para a URL de sandbox
    # (https://sandbox.melhorenvio.com.br/api/v2/me/shipment/calculate)
    # se estiver testando com um token de sandbox.
    MELHOR_ENVIO_URL = "https://www.melhorenvio.com.br/api/v2/me/shipment/calculate"

    def post(self, request):
        destination_cep = request.data.get('cep_destino', '').replace('-', '')
        items = request.data.get('items', [])  # [{ "product_id": "uuid", "quantity": 1 }, ...]

        if not destination_cep or len(destination_cep) != 8:
            return Response({'error': 'CEP de destino inválido.'}, status=status.HTTP_400_BAD_REQUEST)
        if not items:
            return Response({'error': 'Carrinho vazio.'}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Montar a lista de produtos no formato exigido pelo Melhor Envio
        products_payload = []
        for item in items:
            try:
                product = Product.objects.get(id=item['product_id'])
            except Product.DoesNotExist:
                return Response(
                    {'error': f'Produto {item["product_id"]} não encontrado.'},
                    status=status.HTTP_404_NOT_FOUND
                )

            qty = int(item.get('quantity', 1))

            products_payload.append({
                'id': str(product.id),
                'width': float(product.width_cm),
                'height': float(product.height_cm),
                'length': float(product.length_cm),
                'weight': float(product.weight_kg),
                'insurance_value': float(product.price),
                'quantity': qty,
            })

        # 2. Cache (mesmo carrinho + mesmo CEP reaproveita o resultado por 1 hora)
        cache_str = f"{self.ORIGIN_CEP}_{destination_cep}_{products_payload}"
        cache_key = "frete_" + hashlib.md5(cache_str.encode()).hexdigest()

        cached_result = cache.get(cache_key)
        if cached_result:
            return Response(cached_result)

        # 3. Credenciais do Melhor Envio
        # Ajuste os nomes abaixo caso tenha usado outros nomes de variável no .env / Render.
        token = getattr(settings, 'MELHOR_ENVIO_TOKEN', None) or os.environ.get('MELHOR_ENVIO_TOKEN')
        user_agent = getattr(settings, 'MELHOR_ENVIO_USER_AGENT', None) or os.environ.get('MELHOR_ENVIO_USER_AGENT')

        if not token:
            return Response(
                {'error': 'Token do Melhor Envio não configurado no servidor.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        headers = {
            'Authorization': f'Bearer {token}',
            # O Melhor Envio EXIGE um User-Agent identificando app + e-mail de contato.
            'User-Agent': user_agent or 'Auto Pecas App (contato@seudominio.com.br)',
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }

        payload = {
            'from': {'postal_code': self.ORIGIN_CEP},
            'to': {'postal_code': destination_cep},
            'products': products_payload,
            'options': {
                'receipt': False,
                'own_hand': False,
            },
        }

        try:
            response = requests.post(self.MELHOR_ENVIO_URL, json=payload, headers=headers, timeout=10)
        except requests.exceptions.RequestException:
            return Response(
                {'error': 'Serviço de frete indisponível no momento. Tente novamente mais tarde.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        if response.status_code != 200:
            return Response(
                {'error': 'Não foi possível calcular o frete para este CEP.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        data = response.json()

        results = []
        for option in data:
            # Transportadoras/serviços indisponíveis para esta rota vêm com "error" preenchido
            if option.get('error'):
                continue

            price = option.get('custom_price') or option.get('price')
            days = option.get('custom_delivery_time') or option.get('delivery_time')

            if price is None or days is None:
                continue

            company_name = (option.get('company') or {}).get('name', '')
            service_name = option.get('name', '')
            label = f"{company_name} {service_name}".strip()

            results.append({
                'service': label,
                'price': f"{float(price):.2f}".replace('.', ','),
                'days': int(days),
                'warning': None,
            })

        if not results:
            return Response(
                {'error': 'Nenhuma transportadora atende este CEP para os itens informados.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        results.sort(key=lambda r: float(r['price'].replace(',', '.')))

        # Salvar no cache por 1 hora
        cache.set(cache_key, results, 3600)

        return Response(results)


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