from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated, AllowAny

import logging
import requests
import hashlib
from decimal import Decimal
from django.utils.dateparse import parse_datetime
from django.conf import settings
from django.core.cache import cache

from .models import Order
from .serializers import OrderSerializer, ShippingSimulationSerializer
from catalog.models import Product
from .services.mercadopago import MercadoPagoService

logger = logging.getLogger(__name__)

# ==========================================
# 1. VIEWS DE PEDIDOS E CHECKOUT
# ==========================================

class CheckoutView(generics.CreateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer

class OrderListView(generics.ListAPIView):
    queryset = Order.objects.all().order_by('-created_at')
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]


# ==========================================
# 2. VIEW DE INTEGRAÇÃO - MERCADO PAGO
# ==========================================

class OrderPaymentView(APIView):
    def post(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response({'error': 'Pedido não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        payment_method = request.data.get('payment_method')
        if payment_method not in ['card', 'pix']:
            return Response({'error': 'Método de pagamento inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Envia a Order para o Mercado Pago
            mp_response = MercadoPagoService.create_order(order, request.data)

            mp_order_id = str(mp_response.get('id', ''))
            order_status = mp_response.get('status', '').lower()

            order.mercadopago_order_id = mp_order_id
            order.payment_method = payment_method
            order.payment_status = order_status

            # Mapeamento do status
            if order_status == 'processed' or order_status == 'approved':
                order.status = 'PAID'
            elif order_status in ['pending', 'action_required', 'in_process']:
                order.status = 'PENDING'
            elif order_status in ['cancelled', 'rejected', 'expired']:
                order.status = 'CANCELED'

            # Resposta padronizada para o frontend
            response_data = {
                'order_id': str(order.id),
                'mp_order_id': mp_order_id,
                'status': order_status,
                'status_detail': mp_response.get('status_detail', '')
            }

            # Dados do Pix se for pagamento via Pix
            transactions = mp_response.get('transactions', [])
            if payment_method == 'pix' and transactions:
                pix_tx = transactions[0].get('payment_method', {})
                payment_info = transactions[0].get('payment_data', {}) or transactions[0]
                
                qr_code = payment_info.get('qr_code') or pix_tx.get('qr_code')
                qr_code_base64 = payment_info.get('qr_code_base64') or pix_tx.get('qr_code_base64')
                ticket_url = payment_info.get('ticket_url') or pix_tx.get('ticket_url')
                expiration_str = payment_info.get('date_of_expiration') or pix_tx.get('date_of_expiration')

                if expiration_str:
                    order.pix_expiration_date = parse_datetime(expiration_str)

                response_data['pix'] = {
                    'text': qr_code,
                    'qrcode64': qr_code_base64,
                    'ticket_url': ticket_url,
                    'expiration_date': expiration_str
                }

            order.save()
            return Response(response_data, status=status.HTTP_200_OK)

        except requests.exceptions.HTTPError as e:
            error_data = e.response.json() if e.response else {}
            logger.error("Erro no Mercado Pago: %s", error_data)
            return Response({
                'error': error_data.get('message', 'Falha ao processar pagamento junto ao Mercado Pago.')
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception("Erro inesperado ao processar pagamento (order %s)", order_id)
            return Response({'error': 'Erro interno ao processar o pagamento.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class MercadoPagoWebhookView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        payload = request.data
        topic = request.query_params.get('topic') or payload.get('type') or payload.get('action')
        
        mp_order_id = payload.get('data', {}).get('id') or payload.get('id')

        if topic in ['order', 'merchant_order'] or 'order' in str(topic):
            if mp_order_id:
                try:
                    mp_order = MercadoPagoService.get_order(mp_order_id)
                    external_ref = mp_order.get('external_reference')
                    mp_status = mp_order.get('status', '').lower()

                    if external_ref:
                        order = Order.objects.get(id=external_ref)
                        order.payment_status = mp_status

                        if mp_status in ['processed', 'approved']:
                            order.status = 'PAID'
                        elif mp_status in ['cancelled', 'rejected', 'expired']:
                            order.status = 'CANCELED'

                        order.save()
                        return Response({'status': 'updated'}, status=status.HTTP_200_OK)
                except Order.DoesNotExist:
                    logger.warning("Pedido com external_reference %s não encontrado.", external_ref)
                except Exception as e:
                    logger.exception("Erro ao processar webhook do Mercado Pago")

        return Response({'status': 'ignored'}, status=status.HTTP_200_OK)


# ==========================================
# 3. VIEW DE INTEGRAÇÃO - MELHOR ENVIO (FRETE)
# ==========================================

class ShippingSimulationView(APIView):
    ORIGIN_CEP = "89200000" 

    def post(self, request):
        destination_cep = request.data.get('cep_destino', '').replace('-', '')
        items = request.data.get('items', []) # Lista de { "product_id": "uuid", "quantity": 1 }

        if not destination_cep or len(destination_cep) != 8:
            return Response({"error": "CEP de destino inválido."}, status=status.HTTP_400_BAD_REQUEST)
        
        if not items:
            return Response({"error": "O carrinho está vazio."}, status=status.HTTP_400_BAD_REQUEST)

        # Monta um identificador para o Cache baseado no CEP + IDs e Quantidades dos itens
        cache_key_raw = f"{destination_cep}_" + "_".join([f"{item['product_id']}-{item['quantity']}" for item in sorted(items, key=lambda x: x['product_id'])])
        cache_key = hashlib.md5(cache_key_raw.encode('utf-8')).hexdigest()

        cached_shipping = cache.get(cache_key)
        if cached_shipping:
            return Response(cached_shipping, status=status.HTTP_200_OK)

        products_data = []
        for item in items:
            try:
                product = Product.objects.get(id=item['product_id'])
                # A API do melhor envio precisa de medidas minimas para cotar. 
                # Assumindo peso minimo de 0.1 e medidas de 10x10x10 se não houver cadastro.
                products_data.append({
                    "id": str(product.id),
                    "width": float(product.width_cm) if getattr(product, 'width_cm', 0) > 0 else 10,
                    "height": float(product.height_cm) if getattr(product, 'height_cm', 0) > 0 else 10,
                    "length": float(product.length_cm) if getattr(product, 'length_cm', 0) > 0 else 10,
                    "weight": float(product.weight_kg) if getattr(product, 'weight_kg', 0) > 0 else 0.1,
                    "insurance_value": float(product.price),
                    "quantity": item['quantity']
                })
            except Product.DoesNotExist:
                return Response({"error": f"Produto ID {item['product_id']} não encontrado."}, status=status.HTTP_404_NOT_FOUND)

        payload = {
            "from": {"postal_code": self.ORIGIN_CEP},
            "to": {"postal_code": destination_cep},
            "products": products_data
        }

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.MELHOR_ENVIO_TOKEN}",
            "User-Agent": "Aplicação DLS (thiago@dlsautopecas.com.br)"
        }

        try:
            url = f"{settings.MELHOR_ENVIO_URL}/api/v2/me/shipment/calculate"
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            response.raise_for_status()
            
            melhor_envio_data = response.json()
            
            # Filtra apenas os serviços válidos e sem erro. Retorna no contrato padronizado.
            shipping_options = []
            for option in melhor_envio_data:
                if 'error' not in option and option.get('price'):
                    shipping_options.append({
                        "service": option.get("name"),
                        "price": option.get("price"),
                        "deadline_days": option.get("delivery_time")
                    })

            # Salva no cache por 1 hora (3600 segundos) para não estourar os limites da API
            cache.set(cache_key, shipping_options, 3600)

            return Response(shipping_options, status=status.HTTP_200_OK)

        except requests.exceptions.RequestException as e:
            logger.error("Erro na API do Melhor Envio: %s", str(e))
            return Response({"error": "Serviço de frete indisponível no momento."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)