from rest_framework import serializers
from .models import Order, OrderItem
from catalog.models import Product


class OrderItemSerializer(serializers.ModelSerializer):
    product_id = serializers.UUIDField()

    class Meta:
        model = OrderItem
        fields = ["product_id", "quantity"]


# orders/serializers.py

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, write_only=True)
    total = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "customer_name", "customer_email", "customer_cpf", "customer_phone",
            "zip_code", "address", "street", "number", "district", "complement", "city", "state",
            "shipping_service", "shipping_fee", "items", "status", "status_display",
            "created_at", "total",
        ]
        # "address" fica read_only porque agora é gerado automaticamente, não vem mais do frontend
        read_only_fields = ["id", "status", "status_display", "created_at", "total", "address"]

    def get_total(self, obj):
        total_items = sum(item.quantity * item.unit_price for item in obj.items.all())
        return float(total_items + obj.shipping_fee)

    def _build_address_string(self, validated_data):
        # Monta a mesma string única de antes, pra manter tudo que já lê "address" funcionando
        parts = [
            f"{validated_data.get('street', '')}, {validated_data.get('number', '')}".strip(', '),
            validated_data.get('complement', ''),
            validated_data.get('district', ''),
            validated_data.get('city', ''),
            validated_data.get('state', ''),
        ]
        return ' - '.join(p for p in parts if p)

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        validated_data['address'] = self._build_address_string(validated_data)
        order = Order.objects.create(**validated_data)

        for item_data in items_data:
            product = Product.objects.get(id=item_data["product_id"])
            OrderItem.objects.create(
                order=order, product=product,
                quantity=item_data["quantity"], unit_price=product.price,
            )
        return order
        


# SImulacao de frete
class ShippingItemSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class ShippingSimulationSerializer(serializers.Serializer):
    zip_code = serializers.CharField(max_length=9)
    items = ShippingItemSerializer(many=True)
