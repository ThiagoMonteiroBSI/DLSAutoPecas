import json

import requests
from django.conf import settings
from django.core.management.base import BaseCommand

from catalog.models import Product
from orders.services import superfrete


class Command(BaseCommand):
    help = 'Testa a integração de frete com a SuperFrete, passo a passo.'

    def add_arguments(self, parser):
        parser.add_argument('--cep', default='01018020', help='CEP de destino')
        parser.add_argument('--sku', default=None, help='SKU do produto (opcional)')
        parser.add_argument('--qtd', type=int, default=1)

    def handle(self, *args, **opts):
        self._passo1()
        self._passo2()
        self._passo3(opts['cep'], opts['sku'], opts['qtd'])

    def _titulo(self, texto):
        self.stdout.write(self.style.MIGRATE_HEADING(f'\n=== {texto} ==='))

    def _ok(self, texto):
        self.stdout.write(self.style.SUCCESS(texto))

    def _erro(self, texto):
        self.stdout.write(self.style.ERROR(texto))

    # --- 1: token -----------------------------------------------------
    def _passo1(self):
        self._titulo('1. Token e configuração')
        self.stdout.write(f'Base URL : {settings.SUPERFRETE_BASE_URL}')
        self.stdout.write(f'Origem   : {settings.SHIPPING_ORIGIN_POSTAL_CODE}')
        self.stdout.write(f'Serviços : {settings.SUPERFRETE_SERVICES}')
        try:
            user = superfrete.check_token()
            self._ok(f"OK - {user.get('firstname')} {user.get('lastname')} "
                     f"| saldo R$ {user.get('balance')}")
        except Exception as exc:
            self._erro(f'FALHOU: {exc}')
            raise SystemExit(1)

    # --- 2: payload literal da documentação ---------------------------
    def _passo2(self):
        self._titulo('2. Cotação com o payload de exemplo da documentação')
        payload = {
            'from': {'postal_code': settings.SHIPPING_ORIGIN_POSTAL_CODE},
            'to': {'postal_code': '01018020'},
            'services': settings.SUPERFRETE_SERVICES,
            'options': {
                'own_hand': False,
                'receipt': False,
                'insurance_value': 0,
                'use_insurance_value': False,
            },
            'products': [
                {'quantity': 1, 'height': 4, 'width': 3, 'length': 3, 'weight': 0.03}
            ],
        }
        url = f'{settings.SUPERFRETE_BASE_URL.rstrip("/")}/api/v0/calculator'
        resp = requests.post(
            url, json=payload,
            headers={
                'Authorization': f'Bearer {settings.SUPERFRETE_TOKEN}',
                'User-Agent': settings.SUPERFRETE_USER_AGENT,
                'accept': 'application/json',
                'content-type': 'application/json',
            },
            timeout=25,
        )
        self.stdout.write(f'HTTP {resp.status_code}')
        self.stdout.write(resp.text[:2000])
        if resp.ok:
            self._ok('OK - formato do payload confirmado')
        else:
            self._erro('FALHOU - payload enviado:')
            self.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False))

    # --- 3: fluxo real, com produto do banco --------------------------
    def _passo3(self, cep, sku, qtd):
        self._titulo('3. Cotação com produto real do banco')
        produto = (Product.objects.filter(sku=sku).first() if sku
                   else Product.objects.first())
        if not produto:
            self._erro('Nenhum produto cadastrado.')
            return

        self.stdout.write(
            f'{produto.sku} | {produto.name} | R$ {produto.price} | '
            f'{produto.weight_kg} kg | '
            f'{produto.length_cm}x{produto.width_cm}x{produto.height_cm} cm'
        )
        try:
            opcoes = superfrete.quote(cep, [(produto, qtd)])
        except superfrete.SuperFreteError as exc:
            self._erro(f'FALHOU: {exc}')
            return

        if not opcoes:
            self._erro('Nenhuma opção disponível (todas com has_error).')
            return

        for o in opcoes:
            self._ok(
                f"{o['service']:<14} R$ {o['price']:>7.2f}  "
                f"{o['deadline_days']} dia(s)  [{o['company']}]"
            )