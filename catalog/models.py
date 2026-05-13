import uuid
from django.db import models

class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

class Brand(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    
    def __str__(self):
        return self.name

class Category(BaseModel):
    name = models.CharField(max_length=100)
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subcategories')
    
    def __str__(self):
        return f"{self.parent.name} -> {self.name}" if self.parent else self.name

class VehicleCompatibility(BaseModel):
    maker = models.CharField(max_length=100) 
    model = models.CharField(max_length=100) 
    start_year = models.IntegerField()
    end_year = models.IntegerField(null=True, blank=True) 
    
    def __str__(self):
        return f"{self.maker} {self.model} ({self.start_year}-{self.end_year or 'Atual'})"

class Product(BaseModel):
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=50, unique=True)
    oem_code = models.CharField(max_length=100, blank=True, null=True, help_text="Código Original da Montadora")
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)
    weight_kg = models.DecimalField(max_digits=5, decimal_places=3, default=0.0)
    
    
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name='products')
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='products')
    compatibilities = models.ManyToManyField(VehicleCompatibility, related_name='compatible_products')
    
    def __str__(self):
        return f"[{self.sku}] {self.name}"

class ProductImage(BaseModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/') 
    is_main = models.BooleanField(default=False)