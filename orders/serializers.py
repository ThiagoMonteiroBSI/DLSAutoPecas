from rest_framework import serializers
from .models import Order, OrderItem
from catalog.models import Product


class OrderItemSerializer(serializers.ModelSerializer):
    product_id = serializers.UUIDField()

    class Meta:
        model = OrderItem
        fields = ["product_id", "quantity"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, write_only=True)
    total = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "customer_name",
            "customer_email",
            "customer_cpf",
            "zip_code",
            "address",
            "shipping_service",
            "shipping_fee",
            "items",
            "status",
            "status_display",
            "created_at",
            "total",
        ]
        read_only_fields = ["id", "status", "status_display", "created_at", "total"]

    def get_total(self, obj):
        # Calcula o total dos itens + frete
        total_items = sum(item.quantity * item.unit_price for item in obj.items.all())
        return float(total_items + obj.shipping_fee)

    def create(self, validated_data):
        items_data = validated_data.pop("items")
        order = Order.objects.create(**validated_data)

        for item_data in items_data:
            product = Product.objects.get(id=item_data["product_id"])
            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=item_data["quantity"],
                unit_price=product.price,
            )
        return order


# SImulacao de frete
class ShippingItemSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class ShippingSimulationSerializer(serializers.Serializer):
    zip_code = serializers.CharField(max_length=9)
    items = ShippingItemSerializer(many=True)
