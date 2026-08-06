import uuid
from django.db import models
from catalog.models import Product

class Order(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Aguardando Pagamento'),
        ('PAID', 'Pagamento Confirmado'),
        ('SHIPPED', 'Enviado'),
        ('DELIVERED', 'Entregue'),
        ('CANCELED', 'Cancelado'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    customer_name = models.CharField(max_length=255)
    customer_email = models.EmailField()
    customer_cpf = models.CharField(max_length=14)
    customer_phone = models.CharField(max_length=20, blank=True, default='')  # NOVO — o boleto exige

    zip_code = models.CharField(max_length=9)
    address = models.CharField(max_length=255, blank=True, default='')  # mantido, só pra não quebrar telas que já usam
    street = models.CharField(max_length=255, blank=True, default='')       # NOVO
    number = models.CharField(max_length=20, blank=True, default='')        # NOVO
    district = models.CharField(max_length=100, blank=True, default='')     # NOVO
    complement = models.CharField(max_length=100, blank=True, default='')   # NOVO
    city = models.CharField(max_length=100, blank=True, default='')         # NOVO
    state = models.CharField(max_length=2, blank=True, default='')          # NOVO

    shipping_service = models.CharField(max_length=50)
    shipping_fee = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    tracking_code = models.CharField(max_length=100, blank=True, null=True)

    # --- NOVOS CAMPOS PARA MERCADO PAGO ---
    mercadopago_order_id = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    payment_method = models.CharField(max_length=20, blank=True, default='')  # 'pix' ou 'card'
    payment_status = models.CharField(max_length=50, blank=True, default='')   # status retornado do MP (e.g. approved, pending)
    pix_expiration_date = models.DateTimeField(blank=True, null=True)         # Data/hora de expiração do Pix
    # --------------------------------------

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Pedido {self.id} - {self.customer_name} ({self.get_status_display()})"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity}x {self.product.name} (Pedido {self.order.id})"