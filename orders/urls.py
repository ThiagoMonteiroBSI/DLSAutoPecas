from django.urls import path
from . import views

urlpatterns = [
    path('', views.OrderListView.as_view(), name='order-list'),
    path('checkout/', views.CheckoutView.as_view(), name='checkout'),
    path('<uuid:order_id>/pay/', views.OrderPaymentView.as_view(), name='order-pay'),
    path('webhook/mercadopago/', views.MercadoPagoWebhookView.as_view(), name='mercadopago-webhook'),
]