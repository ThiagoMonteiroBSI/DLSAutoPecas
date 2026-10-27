from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'', views.OrderViewSet, basename='order')

urlpatterns = [
    path('shipping/simulate/', views.ShippingQuoteView.as_view(), name='shipping_simulate'),
    path('', include(router.urls)),
]