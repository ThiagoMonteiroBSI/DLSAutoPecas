import requests
from django.conf import settings
from datetime import date, timedelta

def get_headers():
    return {
        "access_token": settings.ASAAS_API_KEY,
        "Content-Type": "application/json"
    }

def create_customer(name, email, phone, cpf):
    url = f"{settings.ASAAS_BASE_URL}/customers"
    payload = {
        "name": name,
        "email": email,
        "phone": phone,
        "cpfCnpj": cpf
    }
    response = requests.post(url, json=payload, headers=get_headers())
    
    if not response.ok:
        raise Exception(f"Erro ao criar cliente no Asaas: {response.text}")
        
    return response.json()["id"]

def create_payment(order, customer_id):
    url = f"{settings.ASAAS_BASE_URL}/payments"
    due_date = (date.today() + timedelta(days=3)).strftime("%Y-%m-%d")
    
    valor_total = 0.0
    
    for item in order.items.all():
        preco = float(item.unit_price)
        quantidade = float(item.quantity)
        valor_total += preco * quantidade
        
    taxa_entrega = float(order.shipping_fee)
    valor_total += taxa_entrega
    
    payload = {
        "customer": customer_id,
        "billingType": "UNDEFINED",
        "value": valor_total,
        "dueDate": due_date,
        "description": f"Pedido {order.id}",
        "externalReference": str(order.id),
        "callback": {
            "successUrl": "https://front-dls.vercel.app/customer-area",
            "autoRedirect": True
        }
    }
    
    response = requests.post(url, json=payload, headers=get_headers())
    
    if not response.ok:
        raise Exception(f"Erro ao criar cobrança no Asaas: {response.text}")
        
    return response.json()["invoiceUrl"]