from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated, AllowAny


import requests
from .services.ipag import IpagService

from .models import Order
from .serializers import OrderSerializer, ShippingSimulationSerializer
from catalog.models import Product # Importação necessária para ler os pesos

class CheckoutView(generics.CreateAPIView):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    # Recomenda-se adicionar permission_classes se não for uma compra como convidado
    # permission_classes = [IsAuthenticated]

class OrderListView(generics.ListAPIView):
    queryset = Order.objects.all().order_by('-created_at')
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]

class ShippingSimulationView(APIView):
    ORIGIN_CEP = "89200000" 

    def post(self, request):
        destination_cep = request.data.get('cep_destino', '').replace('-', '')
        items = request.data.get('items', []) # Lista de { "product_id": "uuid", "quantity": 1 }

        if not destination_cep or len(destination_cep) != 8:
            return Response({'error': 'CEP de destino inválido.'}, status=status.HTTP_400_BAD_REQUEST)
        if not items:
            return Response({'error': 'Carrinho vazio.'}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Obter Produtos e Calcular Peso/Volume Total
        total_weight = Decimal('0.0')
        total_volume = Decimal('0.0')

        for item in items:
            try:
                product = Product.objects.get(id=item['product_id'])
                qty = int(item.get('quantity', 1))
                
                total_weight += product.weight_kg * qty
                
                # Volume do item (C * L * A)
                item_vol = product.length_cm * product.width_cm * product.height_cm
                total_volume += item_vol * qty
            except Product.DoesNotExist:
                return Response({'error': f'Produto {item["product_id"]} não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        # Se o peso for 0, os correios barram. Peso mínimo tarifado geralmente é 0.3kg
        if total_weight < Decimal('0.3'):
            total_weight = Decimal('0.3')

        # 2. Cubagem - Extrair L x W x H da "Caixa Cúbica Equivalente"
        # math.pow(volume, 1/3) dá a aresta de um cubo com aquele volume
        cubic_side = float(total_volume) ** (1/3)
        
        # Respeitar limites MÍNIMOS dos Correios para pacotes
        final_length = max(16.0, cubic_side)
        final_width = max(11.0, cubic_side)
        final_height = max(2.0, cubic_side)

        # Respeitar limite MÁXIMO dos Correios (Soma C+L+A não pode passar de 200cm)
        if (final_length + final_width + final_height) > 200:
            return Response({'error': 'Dimensões totais excedem o limite dos Correios.'}, status=status.HTTP_400_BAD_REQUEST)

        # 3. Caching (Chave baseada na origem, destino, peso e volume)
        # Assim, o mesmo carrinho para o mesmo CEP reaproveita o cálculo por 1 hora
        cache_str = f"{self.ORIGIN_CEP}_{destination_cep}_{total_weight:.2f}_{total_volume:.2f}"
        cache_key = "frete_" + hashlib.md5(cache_str.encode()).hexdigest()
        
        cached_result = cache.get(cache_key)
        if cached_result:
            return Response(cached_result)

        # 4. Requisição para os Correios
        # 04510 = PAC (Sem Contrato) | 04014 = SEDEX (Sem Contrato)
        services = {'PAC': '04510', 'SEDEX': '04014'}
        results = []

        try:
            for name, code in services.items():
                url = "http://ws.correios.com.br/calculador/CalcPrecoPrazo.aspx"
                params = {
                    'nCdEmpresa': '', 'sDsSenha': '',
                    'sCepOrigem': self.ORIGIN_CEP,
                    'sCepDestino': destination_cep,
                    'nVlPeso': str(total_weight),
                    'nCdFormato': '1', # 1 = Formato Caixa/Pacote
                    'nVlComprimento': str(int(final_length)),
                    'nVlAltura': str(int(final_height)),
                    'nVlLargura': str(int(final_width)),
                    'sCdMaoPropria': 'N',
                    'nVlValorDeclarado': '0',
                    'sCdAvisoRecebimento': 'N',
                    'nCdServico': code,
                    'nVlDiametro': '0',
                    'StrRetorno': 'xml',
                    'nIndicaCalculo': '3'
                }
                
                # Timeout de 5 segundos para não travar a API do Django
                response = requests.get(url, params=params, timeout=5)
                
                # Parse do XML
                root = ET.fromstring(response.content)
                c_servico = root.find('cServico')
                
                erro = c_servico.find('Erro').text
                msg_erro = c_servico.find('MsgErro').text
                
                if erro == '0' or erro == '011': # 0 = OK, 011 = OK com aviso (ex: CEP com restrição)
                    valor = c_servico.find('Valor').text
                    prazo = c_servico.find('PrazoEntrega').text
                    
                    results.append({
                        'service': name,
                        'price': valor,
                        'days': int(prazo),
                        'warning': msg_erro if erro == '011' else None
                    })

            if not results:
                return Response({'error': 'Correios não atendem este CEP para as dimensões enviadas.'}, status=status.HTTP_400_BAD_REQUEST)

            # Salvar no Cache por 1 Hora (3600 segundos)
            cache.set(cache_key, results, 3600)
            
            return Response(results)

        except requests.exceptions.RequestException:
            return Response({'error': 'Serviço dos Correios indisponível no momento. Tente novamente mais tarde.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

class PaymentWebhookView(APIView):
    permission_classes = [AllowAny]

    STATUS_MAP = {
        8: 'PAID',       # CAPTURED
        6: 'PAID',       # PARTIAL_CAPTURED
        7: 'CANCELED',   # DECLINED
        3: 'CANCELED',   # CANCELED
        9: 'CANCELED',   # CHARGEBACK
    }

    def post(self, request):
        payload = request.data
        attributes = payload.get('attributes', payload)
        
        ipag_order_id = attributes.get('order_id')
        status_code = attributes.get('status', {}).get('code')

        if not ipag_order_id or status_code is None:
            return Response({"error": "Parâmetros inválidos."}, status=status.HTTP_400_BAD_REQUEST)

        # Recupera o ID original do Django (removendo o sufixo único que adicionamos)
        original_order_id = ipag_order_id.split('-')[0]

        try:
            order = Order.objects.get(id=original_order_id)
            new_status = self.STATUS_MAP.get(status_code)
            
            if new_status:
                order.status = new_status
                order.save()
                
            return Response({"message": "Webhook processado."}, status=status.HTTP_200_OK)
        except Order.DoesNotExist:
            return Response({"error": "Pedido não encontrado."}, status=status.HTTP_404_NOT_FOUND)


class OrderPaymentView(APIView):
    permission_classes = [AllowAny]

    def post(self, request, order_id):
        try:
            order = Order.objects.get(id=order_id)
        except Order.DoesNotExist:
            return Response({'error': 'Pedido não encontrado.'}, status=status.HTTP_404_NOT_FOUND)

        if order.status != 'PENDING':
            return Response({'error': 'Este pedido já foi processado.'}, status=status.HTTP_400_BAD_REQUEST)

        payment_method = request.data.get('payment_method')

        try:
            if payment_method == 'credit_card':
                card_data = request.data.get('card', {})
                required = ['holder', 'number', 'expiry_month', 'expiry_year', 'cvv', 'brand']
                if not all(card_data.get(f) for f in required):
                    return Response({'error': 'Dados do cartão incompletos.'}, status=status.HTTP_400_BAD_REQUEST)
                installments = int(request.data.get('installments', 1))
                result = IpagService.create_card_payment(order, card_data, installments=installments, capture=True)

            elif payment_method == 'pix':
                result = IpagService.create_pix_payment(order)

            elif payment_method == 'boleto':
                due_date = request.data.get('due_date')
                if not due_date:
                    return Response({'error': 'Data de vencimento do boleto é obrigatória.'}, status=status.HTTP_400_BAD_REQUEST)
                result = IpagService.create_boleto_payment(order, due_date)

            else:
                return Response({'error': 'Método de pagamento inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        except requests.exceptions.RequestException:
            return Response({'error': 'Serviço de pagamento indisponível no momento. Tente novamente.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        attributes = result.get('attributes', result)
        status_code = attributes.get('status', {}).get('code')

        if status_code == 8:  # CAPTURED (Cartão)
            order.status = 'PAID'
            order.save()
        elif status_code == 2: # WAITING_PAYMENT (Boleto / Pix)
            order.status = 'PENDING'
            order.save()

        # Resposta padronizada para o Frontend
        response_data = {
            'order_id': str(order.id),
            'status_code': status_code,
            'status_message': attributes.get('status', {}).get('name'),
            'gateway_message': attributes.get('message'),
        }

        # AJUSTE SEGURO: Se a transação for boleto, extrai e envia os dados de impressão
        payment_info = attributes.get('payment', {})
        if payment_info.get('type') == 'boleto':
            boleto_data = payment_info.get('boleto', {})
            response_data['boleto'] = {
                'url': boleto_data.get('url') or boleto_data.get('pdf'),
                'digitable_line': boleto_data.get('digitable_line') or boleto_data.get('linha_digitavel'),
                'barcode': boleto_data.get('barcode') or boleto_data.get('codigo_barras'),
            }

        return Response(response_data, status=status.HTTP_200_OK)