from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Brand, Category, Product, ProductImage, VehicleCompatibility

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'is_superuser', 'is_staff']

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True)
    email = serializers.EmailField(required=True)
    first_name = serializers.CharField(required=True)
    username = serializers.CharField(required=True)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'first_name']

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', '')
        )
        return user

# --- Login com Google (Passo 2) ---
class GoogleAuthSerializer(serializers.Serializer):
    """Valida a entrada da GoogleLoginView: só o ID Token gerado pelo
    Google Identity Services no frontend. Não tem Meta/model porque não
    serializa um objeto — é só validação do payload de entrada."""
    id_token = serializers.CharField(required=True)

class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = '__all__'

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'

class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'is_main', 'product']

class VehicleCompatibilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleCompatibility
        fields = ['maker', 'model', 'start_year', 'end_year']

class ProductListSerializer(serializers.ModelSerializer):
    brand_name = serializers.CharField(source='brand.name', read_only=True)
    category_name = serializers.SerializerMethodField()
    images = ProductImageSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = ['id', 'sku', 'name', 'price', 'stock', 'brand', 'category', 'brand_name', 'category_name', 'images']
        # REMOVIDO o bloco extra_kwargs daqui

    def get_category_name(self, obj):
        return str(obj.category)

class ProductDetailSerializer(serializers.ModelSerializer):
    brand_name = serializers.CharField(source='brand.name', read_only=True)
    category_name = serializers.SerializerMethodField()
    images = ProductImageSerializer(many=True, read_only=True)
    compatibilities = VehicleCompatibilitySerializer(many=True, read_only=True)

    # Campo write-only: recebe os arquivos enviados pelo formulário do site
    # (frontend faz data.append('uploaded_images', file) para cada imagem).
    # Sem esse campo, o DRF ignora silenciosamente os arquivos multipart,
    # já que 'uploaded_images' não corresponde a nenhum campo do model Product.
    uploaded_images = serializers.ListField(
        child=serializers.ImageField(),
        write_only=True,
        required=False
    )

    class Meta:
        model = Product
        fields = [
            'id', 'sku', 'oem_code', 'name', 'description', 
            'price', 'stock', 'weight_kg', 'length_cm', 'width_cm', 'height_cm', # <-- Novos campos
            'brand', 'category', 'brand_name', 'category_name', 'images', 'compatibilities',
            'uploaded_images',
        ]
        # REMOVIDO o bloco extra_kwargs daqui

    def get_category_name(self, obj):
        return str(obj.category)

    def create(self, validated_data):
        images_data = validated_data.pop('uploaded_images', [])
        product = Product.objects.create(**validated_data)
        self._create_images(product, images_data)
        return product

    def update(self, instance, validated_data):
        images_data = validated_data.pop('uploaded_images', [])
        instance = super().update(instance, validated_data)
        self._create_images(instance, images_data)
        return instance

    def _create_images(self, product, images_data):
        if not images_data:
            return

        # Se o produto ainda não tem nenhuma imagem, a primeira enviada
        # agora vira a imagem principal (is_main=True)
        has_existing_images = product.images.exists()

        for index, image_file in enumerate(images_data):
            is_main = (not has_existing_images) and (index == 0)
            ProductImage.objects.create(
                product=product,
                image=image_file,
                is_main=is_main
            )