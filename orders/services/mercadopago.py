import mercadopago
from django.conf import settings

def get_mercadopago_client():
    return mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)

def create_payment_preference(order):
    sdk = get_mercadopago_client()
    
    preference_data = {
        "items": [
            {
                "title": f"Pedido {order.id}",
                "quantity": 1,
                "unit_price": float(order.total_price)
            }
        ],
        "payer": {
            "name": order.customer_name,
            "email": order.customer_email
        },
        "back_urls": {
            "success": f"{settings.FRONTEND_URL}/customer-area",
            "failure": f"{settings.FRONTEND_URL}/checkout",
            "pending": f"{settings.FRONTEND_URL}/checkout"
        },
        "auto_return": "approved",
        "external_reference": str(order.id)
    }
    
    result = sdk.preference().create(preference_data)
    return result["response"]["id"]