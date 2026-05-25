from django.urls import path
from . import views

urlpatterns = [
    path('', views.OrderListView.as_view(), name='order-list'),
    path('checkout/', views.CheckoutView.as_view(), name='checkout'),
    path('shipping/simulate/', views.ShippingSimulationView.as_view(), name='shipping-simulate'), 
]