from django.urls import path
from . import views

urlpatterns = [
    path('products/', views.ProductListView.as_view(), name='product-list'),
    path('products/<uuid:id>/', views.ProductDetailView.as_view(), name='product-detail'),
]