from rest_framework import viewsets, filters, generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.auth.models import User
from django.db.models import Sum

from .models import Product, Brand, Category, ProductImage
from orders.models import Order # Certifique-se de que o app orders possui essa model
from .serializers import (
    ProductListSerializer, ProductDetailSerializer, BrandSerializer, 
    CategorySerializer, ProductImageSerializer, UserSerializer, RegisterSerializer
)

class UserMeView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer

class BrandViewSet(viewsets.ModelViewSet):
    queryset = Brand.objects.all()
    serializer_class = BrandSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [permissions.IsAdminUser]
        return [permission() for permission in permission_classes]

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [permissions.IsAdminUser]
        return [permission() for permission in permission_classes]

class ProductImageViewSet(viewsets.ModelViewSet):
    queryset = ProductImage.objects.all()
    serializer_class = ProductImageSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [permissions.IsAdminUser]
        return [permission() for permission in permission_classes]

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all().order_by('-created_at')
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['name', 'sku', 'oem_code']
    filterset_fields = ['brand', 'category']
    lookup_field = 'id'

    def get_serializer_class(self):
        if self.action == 'list':
            return ProductListSerializer
        return ProductDetailSerializer
    
    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [permissions.IsAdminUser]
        return [permission() for permission in permission_classes]

# --- NOVA VIEW DO DASHBOARD ---
class DashboardResumoView(APIView):
    permission_classes = [AllowAny] # Permissão liberada para facilitar, mude se precisar

    def get(self, request):
        periodo = request.query_params.get('periodo', 'mes')
        
        # Aqui você pode aplicar os filtros de data usando o 'periodo' no futuro.
        orders = Order.objects.all()

        # 1. Cálculo Seguro do Faturamento Total (Itens + Frete)
        faturamento_total = 0.0
        for order in orders:
            # Multiplica a quantidade pelo preço de cada item vinculado a este pedido
            total_itens = sum(item.quantity * item.unit_price for item in order.items.all())
            faturamento_total += float(total_itens) + float(order.shipping_fee)

        # 2. Estatísticas Gerais
        pedidos_realizados = orders.count()
        novos_clientes = User.objects.filter(is_staff=False).count()
        produtos_ativos = Product.objects.count()

        # 3. Últimos 5 Pedidos Formatados
        ultimos_pedidos_qs = orders.order_by('-created_at')[:5]
        ultimos_pedidos = []
        
        for pedido in ultimos_pedidos_qs:
            total_itens = sum(item.quantity * item.unit_price for item in pedido.items.all())
            total_pedido = float(total_itens) + float(pedido.shipping_fee)
            
            ultimos_pedidos.append({
                'id': str(pedido.id),
                'cliente_nome': pedido.customer_name, # Lendo o campo correto
                'data_criacao': pedido.created_at,
                'status': pedido.status,
                'status_display': pedido.get_status_display(),
                'total': total_pedido
            })

        return Response({
            'estatisticas': {
                'faturamento_total': faturamento_total,
                'pedidos_realizados': pedidos_realizados,
                'novos_clientes': novos_clientes,
                'produtos_ativos': produtos_ativos
            },
            'ultimos_pedidos': ultimos_pedidos,
            'produtos_mais_vendidos': [] # Implementação futura
        })