from django.contrib import admin
from .models import Order, OrderItem

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0  
    readonly_fields = ('product', 'quantity', 'unit_price')
    
    def has_add_permission(self, request, obj=None):
        return False    
    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer_name', 'status', 'created_at')
    list_filter = ('status', 'created_at', 'shipping_service')
    search_fields = ('id', 'customer_name', 'customer_email', 'customer_cpf', 'tracking_code')
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines = [OrderItemInline]