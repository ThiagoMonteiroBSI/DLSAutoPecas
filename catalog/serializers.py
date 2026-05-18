from rest_framework import serializers
from .models import Product, ProductImage, VehicleCompatibility

class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'is_main']

class VehicleCompatibilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleCompatibility
        fields = ['maker', 'model', 'start_year', 'end_year']


class ProductListSerializer(serializers.ModelSerializer):
    brand_name = serializers.CharField(source='brand.name', read_only=True)
    category_name = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ['id', 'sku', 'name', 'price', 'stock', 'brand_name', 'category_name']

    def get_category_name(self, obj):
        return str(obj.category) 
    
class ProductDetailSerializer(serializers.ModelSerializer):
    brand_name = serializers.CharField(source='brand.name', read_only=True)
    category_name = serializers.SerializerMethodField()
    images = ProductImageSerializer(many=True, read_only=True) 
    compatibilities = VehicleCompatibilitySerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            'id', 'sku', 'oem_code', 'name', 'description', 
            'price', 'stock', 'weight_kg', 'brand_name', 
            'category_name', 'images', 'compatibilities'
        ]

    def get_category_name(self, obj):
        return str(obj.category)