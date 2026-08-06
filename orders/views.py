from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated, AllowAny

import logging
import requests
from django.utils.dateparse import parse_datetime
from django.conf import settings

from .models import Order
from .serializers import OrderSerializer
from .services.mercadopago import MercadoPagoService

logger = logging.getLogger(__name__)

class CheckoutView(generics.CreateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer

class OrderListView(generics.ListAPIView):
    queryset = Order.objects.all().order_by('-created_at')
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

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
        
        # O ID da ordem pode vir em data.id ou id do payload
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