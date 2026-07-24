import logging
import re
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


# Doc: "Status da Transação"
IPAG_STATUS = {
    1: "CREATED",
    2: "WAITING_PAYMENT",
    3: "CANCELED",
    4: "IN_ANALYSIS",
    5: "PRE_AUTHORIZED",
    6: "PARTIAL_CAPTURED",
    7: "DECLINED",
    8: "CAPTURED",
    9: "CHARGEBACK",
    10: "IN_DISPUTE",
}


class IpagService:
    BASE_URL = settings.IPAG_BASE_URL

    @classmethod
    def _headers(cls):
        return {
            "Content-Type": "application/json",
            "x-api-version": "2",
        }

    @classmethod
    def _auth(cls):
        return (settings.IPAG_API_ID, settings.IPAG_API_KEY)

    @classmethod
    def _calculate_total(cls, order):
        # Mesma conta que o OrderSerializer.get_total() já faz
        items_total = sum(
            item.quantity * item.unit_price for item in order.items.all()
        )
        return float(items_total + order.shipping_fee)

    @classmethod
    def _build_products(cls):
        return [
            {
                "name": item.product.name,
                "description": (
                    item.product.description or item.product.name
                )[:255],
                "unit_price": float(item.unit_price),
                "quantity": item.quantity,
                "sku": item.product.sku,
            }
            for item in order.items.all()
        ]

    @classmethod
    def _post(cls, path, payload):
        response = requests.post(
            f"{cls.BASE_URL}{path}",
            json=payload,
            headers=cls._headers(),
            auth=cls._auth(),
            timeout=15,
        )
        response.raise_for_status()
        return response.json()

    @classmethod
    def create_card_payment(
        cls,
        order,
        card_data,
        installments=1,
        capture=True,
    ):
        # Cria um ID único curto para evitar o erro
        # "transaction_order_id_must_be_unique"
        # e respeitar o limite de 16 caracteres da iPag.
        short_id = str(order.id)[:6]
        unique_order_id = f"{short_id}-{hex(int(time.time()))[2:]}"[:16]

        payload = {
            "amount": float(cls._calculate_total(order)),
            "callback_url": settings.IPAG_CALLBACK_URL,
            "order_id": unique_order_id,
            "payment": {
                "type": "card",
                "method": card_data["brand"],
                "installments": int(installments),
                "capture": capture,
                "card": {
                    "holder": card_data["holder"],
                    "number": re.sub(r"\D", "", card_data["number"]),
                    "expiry_month": card_data["expiry_month"],
                    "expiry_year": card_data["expiry_year"],
                    "cvv": card_data["cvv"],
                },
            },
            "customer": {
                "name": order.customer_name,
                "cpf_cnpj": re.sub(r"\D", "", order.customer_cpf),
                "email": order.customer_email,
                "phone": re.sub(r"\D", "", order.customer_phone),
                "billing_address": {
                    "street": order.street,
                    "number": order.number,
                    "district": order.district,
                    "complement": order.complement or "",
                    "city": order.city,
                    "state": order.state,
                    "zipcode": re.sub(r"\D", "", order.zip_code),
                },
            },
            "products": cls._build_products(order),
        }

        return cls._post("/service/payment", payload)

    @classmethod
    def create_pix_payment(cls, order):
        import re
        import uuid

        # Gera ID único de até 16 caracteres para evitar duplicidade
        short_id = str(order.id)[:6]
        unique_order_id = f"{short_id}-{uuid.uuid4().hex[:8]}"[:16]

        payload = {
            'amount': float(cls._calculate_total(order)),
            'callback_url': settings.IPAG_CALLBACK_URL,
            'order_id': unique_order_id,
            'payment': {
                'type': 'pix',
                'method': 'pix',
                'pix_expires_in': 1440  # OBRIGATÓRIO: Exatamente como na documentação (em minutos)
            },
            'customer': {
                'name': order.customer_name,
                'cpf_cnpj': re.sub(r'\D', '', order.customer_cpf),
                'email': order.customer_email,
                'phone': re.sub(r'\D', '', order.customer_phone),
                'billing_address': {
                    'street': order.street,
                    'number': order.number,
                    'district': order.district,
                    'complement': order.complement or '',
                    'city': order.city,
                    'state': order.state,
                    'zipcode': re.sub(r'\D', '', order.zip_code),
                },
            },
            'products': cls._build_products(order),
        }
        return cls._post('/service/payment', payload)