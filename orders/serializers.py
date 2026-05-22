from rest_framework import serializers
from .models import Order, OrderItem
from catalog.models import Product

class OrderItemSerializer(serializers.ModelSerializer):
    product_id = serializers.UUIDField()

    class Meta:
        model = OrderItem
        fields = ['product_id', 'quantity']

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, write_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'customer_name', 'customer_email', 'customer_cpf',
            'zip_code', 'address', 'shipping_service', 'shipping_fee', 'items'
        ]
        read_only_fields = ['id']

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        order = Order.objects.create(**validated_data)
        
        for item_data in items_data:
            product = Product.objects.get(id=item_data['product_id'])

            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=item_data['quantity'],
                unit_price=product.price
            )
        
        return order