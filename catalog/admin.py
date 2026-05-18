from django.contrib import admin
from .models import Brand, Categoria, VehicleCompatibility, Product, ProductImage

class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('sku', 'name', 'brand', 'price', 'stock')
    search_fields = ('sku', 'name', 'oem_code')
    list_filter = ('brand', 'category')
    inlines = [ProductImageInline]
    filter_horizontal = ('compatibilities',) 


admin.site.register(Brand)
admin.site.register(Categoria)
admin.site.register(VehicleCompatibility)

#RODAR MAKEMIGRATIONS E MIGRATE 
#RODAR COMANDO 
#pdm add Pillow django-cloudinary-storage cloudinary django-environ

#RODAR COMANDO ABAIXO 
#pdm add djangorestframework django-cors-headers