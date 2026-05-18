from rest_framework import serializers
from .models import Product

class ProductListSerializer(serializers.ModelSerializer):
    brand_name = serializers.CharField(source='brand.name', read_only=True)
    category_name = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ['id', 'sku', 'name', 'price', 'stock', 'brand_name', 'category_name']

    def get_category_name(self, obj):
        return str(obj.category) 