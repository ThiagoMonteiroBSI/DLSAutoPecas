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
    path('auth/google/', views.GoogleLoginView.as_view(), name='auth_google'),  # Login com Google (Passo 2)
    path('dashboard/resumo/', views.DashboardResumoView.as_view(), name='dashboard_resumo'),
    path('customers/', views.CustomerListView.as_view(), name='customer_list'),
    path('customers/<str:pk>/', views.CustomerDetailView.as_view(), name='customer_detail'),
    path('', include(router.urls)),
]