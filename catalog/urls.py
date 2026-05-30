from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'brands', views.BrandViewSet, basename='brand')
router.register(r'categories', views.CategoryViewSet, basename='category')
router.register(r'products', views.ProductViewSet, basename='product')
router.register(r'images', views.ProductImageViewSet, basename='productimage')

urlpatterns = [
    path('auth/me/', views.UserMeView.as_view(), name='auth_me'),
    path('auth/register/', views.RegisterView.as_view(), name='auth_register'),
    path('', include(router.urls)),
]