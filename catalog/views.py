from rest_framework import viewsets, filters, generics, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.auth.models import User
from django.db.models import Sum

from .models import Product, Brand, Category, ProductImage
from orders.models import Order
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

class DashboardResumoView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        periodo = request.query_params.get('periodo', 'mes')
        orders = Order.objects.all()

        faturamento_total = 0.0
        for order in orders:
            total_itens = sum(item.quantity * item.unit_price for item in order.items.all())
            faturamento_total += float(total_itens) + float(order.shipping_fee)

        pedidos_realizados = orders.count()
        novos_clientes = User.objects.filter(is_staff=False).count()
        produtos_ativos = Product.objects.count()

        ultimos_pedidos_qs = orders.order_by('-created_at')[:5]
        ultimos_pedidos = []
        
        for pedido in ultimos_pedidos_qs:
            total_itens = sum(item.quantity * item.unit_price for item in pedido.items.all())
            total_pedido = float(total_itens) + float(pedido.shipping_fee)
            
            ultimos_pedidos.append({
                'id': str(pedido.id),
                'cliente_nome': pedido.customer_name,
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
            'produtos_mais_vendidos': []
        })

class CustomerListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        clientes_dict = {}
        
        usuarios = User.objects.filter(is_staff=False)
        for u in usuarios:
            nome_completo = f"{u.first_name} {u.last_name}".strip() or u.username
            clientes_dict[u.email] = {
                'id': str(u.id),
                'nome': nome_completo,
                'email': u.email,
                'is_active': u.is_active,
                'data_cadastro': u.date_joined,
                'total_pedidos': 0,
                'cpf': '',
                'telefone': ''
            }
            
        pedidos = Order.objects.all()
        for p in pedidos:
            email = p.customer_email
            if email in clientes_dict:
                clientes_dict[email]['total_pedidos'] += 1
                if not clientes_dict[email]['cpf'] and p.customer_cpf:
                    clientes_dict[email]['cpf'] = p.customer_cpf
                if not clientes_dict[email]['nome'] or clientes_dict[email]['nome'] == email:
                    clientes_dict[email]['nome'] = p.customer_name
            else:
                clientes_dict[email] = {
                    'id': str(p.id),
                    'nome': p.customer_name,
                    'email': email,
                    'is_active': True,
                    'data_cadastro': p.created_at,
                    'total_pedidos': 1,
                    'cpf': p.customer_cpf,
                    'telefone': ''
                }
                
        resultados = list(clientes_dict.values())
        resultados.sort(key=lambda x: x['data_cadastro'], reverse=True)
        
        return Response(resultados)

    def post(self, request):
        nome = request.data.get('nome', '')
        email = request.data.get('email', '')
        
        if not email:
            return Response({"erro": "E-mail é obrigatório"}, status=400)
            
        if User.objects.filter(email=email).exists():
            return Response({"erro": "Este e-mail já está cadastrado"}, status=400)
            
        nomes = nome.split(' ', 1)
        first_name = nomes[0]
        last_name = nomes[1] if len(nomes) > 1 else ''
        
        user = User.objects.create(
            username=email,
            email=email,
            first_name=first_name,
            last_name=last_name,
            is_active=True
        )
        user.set_unusable_password()
        user.save()
        
        return Response({"mensagem": "Cliente adicionado com sucesso"})


class CustomerDetailView(APIView):
    permission_classes = [permissions.AllowAny]

    def put(self, request, pk):
        nome = request.data.get('nome', '')
        cpf = request.data.get('cpf', '')
        status_req = request.data.get('status', 'active')
        
        if str(pk).isdigit():
            try:
                user = User.objects.get(id=pk)
                nomes = nome.split(' ', 1)
                user.first_name = nomes[0]
                user.last_name = nomes[1] if len(nomes) > 1 else ''
                user.is_active = (status_req == 'active')
                user.save()
                return Response({"mensagem": "Cliente atualizado com sucesso"})
            except User.DoesNotExist:
                return Response({"erro": "Usuário não encontrado"}, status=404)
        else:
            try:
                order = Order.objects.get(id=pk)
                email = order.customer_email
                Order.objects.filter(customer_email=email).update(
                    customer_name=nome,
                    customer_cpf=cpf
                )
                return Response({"mensagem": "Cliente convidado atualizado"})
            except Order.DoesNotExist:
                return Response({"erro": "Convidado não encontrado"}, status=404)

    def delete(self, request, pk):
        if str(pk).isdigit():
            try:
                user = User.objects.get(id=pk)
                user.delete()
                return Response({"mensagem": "Cliente excluído com sucesso"})
            except User.DoesNotExist:
                return Response({"erro": "Usuário não encontrado"}, status=404)
        else:
            return Response({"erro": "Não é possível excluir clientes convidados que possuem vínculos a pedidos."}, status=400)