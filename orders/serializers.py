from decimal import Decimal

from rest_framework import serializers

from .models import Order, OrderItem
from catalog.models import Product
from .services import superfrete


class OrderItemSerializer(serializers.ModelSerializer):
    product_id = serializers.UUIDField()

    class Meta:
        model = OrderItem
        fields = ["product_id", "quantity"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, write_only=True)
    total = serializers.SerializerMethodField()
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    shipping_service_id = serializers.IntegerField()

    class Meta:
        model = Order
        fields = [
            "id", "customer_name", "customer_email", "customer_cpf", "customer_phone",
            "zip_code", "address", "street", "number", "district", "complement", "city", "state",
            "shipping_service", "shipping_service_id", "shipping_fee", "shipping_deadline_days",
            "items", "status", "status_display", "created_at", "total",
        ]
        read_only_fields = [
            "id", "status", "status_display", "created_at", "total", "address",
            "shipping_fee", "shipping_service", "shipping_deadline_days",
        ]

    def get_total(self, obj):
        total_items = sum((item.quantity * item.unit_price for item in obj.items.all()), 0)
        return float(total_items) + float(obj.shipping_fee)

    def _build_address_string(self, validated_data):
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
        service_id = validated_data.pop("shipping_service_id")

        quantities = {}
        for item in items_data:
            pid = item["product_id"]
            quantities[pid] = quantities.get(pid, 0) + item["quantity"]

        products = {p.id: p for p in Product.objects.filter(id__in=quantities.keys())}
        if len(products) != len(quantities):
            raise serializers.ValidationError(
                {"items": "Um ou mais produtos não foram encontrados."}
            )

        cart_lines = [(p, quantities[p.id]) for p in products.values()]

        # Recota no servidor. O valor enviado pelo frontend é ignorado.
        try:
            options = superfrete.quote(validated_data["zip_code"], cart_lines)
        except superfrete.SuperFreteError as exc:
            raise serializers.ValidationError({"shipping": str(exc)})

        chosen = next((o for o in options if o["service_id"] == service_id), None)
        if chosen is None:
            raise serializers.ValidationError({
                "shipping": "A opção de frete escolhida não está mais disponível. "
                            "Recalcule o frete e tente novamente."
            })

        validated_data["shipping_service_id"] = chosen["service_id"]
        validated_data["shipping_service"] = chosen["service"]
        validated_data["shipping_fee"] = Decimal(str(chosen["price"]))
        validated_data["shipping_deadline_days"] = chosen["deadline_days"]
        validated_data["address"] = self._build_address_string(validated_data)

        order = Order.objects.create(**validated_data)
        for pid, qty in quantities.items():
            product = products[pid]
            OrderItem.objects.create(
                order=order, product=product,
                quantity=qty, unit_price=product.price,
            )
        return order


class ShippingItemSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class ShippingSimulationSerializer(serializers.Serializer):
    zip_code = serializers.CharField(max_length=9)
    items = ShippingItemSerializer(many=True, allow_empty=False)

    def validate_zip_code(self, value):
        digits = ''.join(c for c in value if c.isdigit())
        if len(digits) != 8:
            raise serializers.ValidationError('CEP deve conter 8 dígitos.')
        return digits