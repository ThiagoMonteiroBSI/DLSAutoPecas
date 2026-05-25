from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .serializers import ShippingSimulationSerializer
from rest_framework import generics
from .models import Order
from .serializers import OrderSerializer
from rest_framework.permissions import IsAuthenticated

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