import logging
from decimal import Decimal

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 25
MAX_TOTAL_WEIGHT_KG = Decimal('30')      # teto de PAC/SEDEX
MIN_INSURANCE_VALUE = Decimal('24.50')   # mínimo de PAC/SEDEX


class SuperFreteError(Exception):
    """Falha ao cotar. A mensagem é segura para exibir ao cliente."""


def _headers():
    if not settings.SUPERFRETE_TOKEN:
        raise SuperFreteError('Serviço de frete não configurado.')
    return {
        'Authorization': f'Bearer {settings.SUPERFRETE_TOKEN}',
        'User-Agent': settings.SUPERFRETE_USER_AGENT,
        'accept': 'application/json',
        'content-type': 'application/json',
    }


def normalize_postal_code(value):
    """A API aceita XXXXX-XXX ou XXXXXXXX. Normalizamos para 8 dígitos."""
    digits = ''.join(c for c in str(value) if c.isdigit())
    if len(digits) != 8:
        raise SuperFreteError('CEP inválido. Informe 8 dígitos.')
    return digits


def _build_products(cart_lines):
    """
    cart_lines: lista de (Product, quantity).
    Enviamos as dimensões REAIS de cada item. A API monta a caixa ideal.
    """
    missing = []
    products = []
    total_weight = Decimal('0')
    total_value = Decimal('0')

    for product, quantity in cart_lines:
        if not product.weight_kg or product.weight_kg <= 0:
            missing.append(product.sku)
            continue

        products.append({
            'quantity': int(quantity),
            'height': float(product.height_cm),
            'width': float(product.width_cm),
            'length': float(product.length_cm),
            'weight': float(product.weight_kg),
        })
        total_weight += Decimal(str(product.weight_kg)) * quantity
        total_value += Decimal(str(product.price)) * quantity

    if missing:
        logger.error('Produtos sem peso cadastrado: %s', ', '.join(missing))
        raise SuperFreteError(
            'Alguns produtos do carrinho estão sem peso cadastrado. '
            'Entre em contato pelo WhatsApp para calcular o frete.'
        )

    if total_weight > MAX_TOTAL_WEIGHT_KG:
        raise SuperFreteError(
            'O peso total do pedido ultrapassa 30 kg, limite dos Correios. '
            'Entre em contato pelo WhatsApp para cotar uma transportadora.'
        )

    return products, total_value


def quote(destination_postal_code, cart_lines):
    products, total_value = _build_products(cart_lines)

    # O seguro só é aplicado quando use_insurance_value é true.
    # Abaixo do mínimo de PAC/SEDEX (R$ 24,50) desligamos para não gerar erro.
    use_insurance = (
        settings.SUPERFRETE_USE_INSURANCE and total_value >= MIN_INSURANCE_VALUE
    )

    payload = {
        'from': {'postal_code': settings.SHIPPING_ORIGIN_POSTAL_CODE},
        'to': {'postal_code': normalize_postal_code(destination_postal_code)},
        'services': settings.SUPERFRETE_SERVICES,
        'options': {
            'own_hand': False,
            'receipt': False,
            'insurance_value': float(total_value) if use_insurance else 0,
            'use_insurance_value': use_insurance,
        },
        'products': products,
    }

    url = f'{settings.SUPERFRETE_BASE_URL.rstrip("/")}/api/v0/calculator'

    try:
        response = requests.post(
            url, json=payload, headers=_headers(), timeout=TIMEOUT_SECONDS
        )
    except requests.Timeout:
        logger.warning('Timeout na SuperFrete')
        raise SuperFreteError('O cálculo de frete demorou demais. Tente novamente.')
    except requests.RequestException as exc:
        logger.exception('Falha de conexão com a SuperFrete: %s', exc)
        raise SuperFreteError('Não foi possível calcular o frete no momento.')

    if not response.ok:
        # A API retorna 400 com corpo vazio; logamos o payload para diagnóstico.
        logger.error(
            'SuperFrete HTTP %s | resposta: %s | payload: %s',
            response.status_code, response.text[:500], payload,
        )
        raise SuperFreteError('Não foi possível calcular o frete no momento.')

    return _parse(response.json())


def _parse(data):
    """A resposta é um array; serviços indisponíveis vêm com has_error=True."""
    if not isinstance(data, list):
        logger.error('Resposta inesperada da SuperFrete: %s', str(data)[:500])
        raise SuperFreteError('Não foi possível calcular o frete no momento.')

    options = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if item.get('has_error'):
            logger.info('Serviço indisponível: %s', item.get('name'))
            continue
        if item.get('price') in (None, ''):
            continue

        try:
            price = float(Decimal(str(item['price'])))
        except (TypeError, ValueError):
            continue

        delivery_range = item.get('delivery_range') or {}
        options.append({
            'service_id': item.get('id'),
            'service': item.get('name', 'Entrega'),
            'company': (item.get('company') or {}).get('name', ''),
            'price': price,
            'deadline_days': item.get('delivery_time'),
            'delivery_min': delivery_range.get('min'),
            'delivery_max': delivery_range.get('max'),
        })

    options.sort(key=lambda o: o['price'])
    return options


def check_token():
    """Smoke test: valida o token sem gastar nada. Use no shell do Django."""
    url = f'{settings.SUPERFRETE_BASE_URL.rstrip("/")}/api/v0/user'
    response = requests.get(url, headers=_headers(), timeout=TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()