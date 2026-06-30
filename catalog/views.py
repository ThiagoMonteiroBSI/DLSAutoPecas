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
    """
    Endpoint dedicado para fornecer dados sumarizados ao dashboard administrativo.
    """
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        # 1. Cálculos de Estatísticas Gerais
        faturamento_dict = Order.objects.filter(status='PAID').aggregate(Sum('total'))
        faturamento_total = faturamento_dict['total__sum'] or 0.00
        
        pedidos_realizados = Order.objects.count()
        novos_clientes = User.objects.filter(is_staff=False).count()
        
        # Filtra por produtos ativos (assumindo que sua model Product tenha o campo 'is_active' ou 'ativo')
        # Ajuste o nome do campo se necessário na sua model
        produtos_ativos = Product.objects.filter(is_active=True).count() if hasattr(Product, 'is_active') else Product.objects.count()

        # 2. Últimos Pedidos
        ultimos_pedidos_qs = Order.objects.order_by('-created_at')[:5]
        ultimos_pedidos = []
        for pedido in ultimos_pedidos_qs:
            ultimos_pedidos.append({
                'id': pedido.id,
                'cliente_nome': pedido.user.username if pedido.user else "Convidado",
                'data_criacao': pedido.created_at,
                'status': pedido.status,
                'total': float(pedido.total) if hasattr(pedido, 'total') else 0
            })

        return Response({
            'estatisticas': {
                'faturamento_total': faturamento_total,
                'pedidos_realizados': pedidos_realizados,
                'novos_clientes': novos_clientes,
                'produtos_ativos': produtos_ativos
            },
            'ultimos_pedidos': ultimos_pedidos,
            'produtos_mais_vendidos': [] # TODO: Implementar lógica de agregação de vendas no futuro
        })