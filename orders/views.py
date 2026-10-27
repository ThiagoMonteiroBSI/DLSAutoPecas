import traceback

from rest_framework import viewsets, status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response

from catalog.models import Product
from .models import Order
from .serializers import OrderSerializer, ShippingSimulationSerializer
from .services.asaas import create_customer, create_payment
from .services import superfrete


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = serializer.save()

        try:
            customer_id = create_customer(
                name=order.customer_name,
                email=order.customer_email,
                phone=order.customer_phone,
                cpf=order.customer_cpf
            )
            invoice_url = create_payment(order, customer_id)

            return Response(
                {"order": serializer.data, "invoice_url": invoice_url},
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            order.delete()
            error_details = traceback.format_exc()
            return Response(
                {"error": f"{str(e)} \n\nDetalhes Tecnicos:\n{error_details}"},
                status=status.HTTP_400_BAD_REQUEST
            )


class ShippingQuoteView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ShippingSimulationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        quantities = {}
        for item in data['items']:
            pid = item['product_id']
            quantities[pid] = quantities.get(pid, 0) + item['quantity']

        products = Product.objects.filter(id__in=quantities.keys())
        if len(products) != len(quantities):
            return Response(
                {'error': 'Um ou mais produtos do carrinho não foram encontrados.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cart_lines = [(p, quantities[p.id]) for p in products]

        try:
            options = superfrete.quote(data['zip_code'], cart_lines)
        except superfrete.SuperFreteError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if not options:
            return Response(
                {'error': 'Nenhuma opção de entrega disponível para este CEP. '
                          'Entre em contato pelo WhatsApp.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(options)