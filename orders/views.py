from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import ShippingSimulationSerializer
from rest_framework import generics
from .models import Order
from .serializers import OrderSerializer
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import AllowAny

class CheckoutView(generics.CreateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer

class ShippingSimulationView(APIView):
    def post(self, request):
        serializer = ShippingSimulationSerializer(data=request.data)
        
        if serializer.is_valid():
            zip_code = serializer.validated_data['zip_code']
            items = serializer.validated_data['items']
            
            # TODO:  fazer um loop em 'items' para somar o 'weight_kg'
            
            mock_shipping_options = [
                {"service": "PAC (Correios)", "price": "35.50", "deadline_days": 7},
                {"service": "SEDEX (Correios)", "price": "78.90", "deadline_days": 3},
                {"service": "Jadlog Package", "price": "42.00", "deadline_days": 5}
            ]
            
            return Response(mock_shipping_options, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    from rest_framework.permissions import IsAuthenticated

class OrderListView(generics.ListAPIView):

    queryset = Order.objects.all().order_by('-created_at')
    serializer_class = OrderSerializer
    
    permission_classes = [IsAuthenticated]



class PaymentWebhookView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):
        payload = request.data

        order_id = payload.get('reference_id') 
        payment_status = payload.get('status') 

        if not order_id or not payment_status:
            return Response({"error": "Payload inválido"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            order = Order.objects.get(id=order_id)

            if payment_status in ['CONFIRMED', 'RECEIVED', 'PAID']:
                order.status = 'PAID'
            elif payment_status in ['REFUNDED', 'CANCELED']:
                order.status = 'CANCELED'
            
            order.save()
            
            return Response({"message": "Webhook recebido e processado"}, status=status.HTTP_200_OK)

        except Order.DoesNotExist:
            return Response({"error": "Pedido não encontrado"}, status=status.HTTP_404_NOT_FOUND)