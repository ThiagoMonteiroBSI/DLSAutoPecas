from rest_framework import generics, filters
from django_filters.rest_framework import DjangoFilterBackend
from .models import Product
from .serializers import ProductListSerializer, ProductDetailSerializer

class ProductDetailView(generics.RetrieveAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductDetailSerializer
    lookup_field = 'id' #Procurar o produto pelo id

class ProductListView(generics.ListAPIView):
    queryset = Product.objects.all().order_by('-created_at')
    serializer_class = ProductListSerializer
    #FILTROS
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['name', 'sku', 'oem_code']
    filterset_fields = ['brand', 'category']

    