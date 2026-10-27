import os
import environ
import dj_database_url
from pathlib import Path
from datetime import timedelta

env = environ.Env(DEBUG=(bool, False))
BASE_DIR = Path(__file__).resolve().parent.parent
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

SECRET_KEY = env('SECRET_KEY')
DEBUG = env('DEBUG')

ALLOWED_HOSTS = ['localhost', '127.0.0.1', env('RENDER_EXTERNAL_HOSTNAME', default='')]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'cloudinary',
    'rest_framework',
    'django_filters',
    'catalog',
    'cloudinary_storage',
    'orders',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'setup.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'setup.wsgi.application'

DATABASES = {
    'default': dj_database_url.config(
        default='sqlite:///' + str(BASE_DIR / 'db.sqlite3'),
        conn_max_age=600
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
STORAGES = {
    "default": {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

CLOUDINARY_STORAGE = {
    "CLOUD_NAME": env('CLOUDINARY_CLOUD_NAME'),
    "API_KEY": env('CLOUDINARY_API_KEY'),
    "API_SECRET": env('CLOUDINARY_API_SECRET'),
}

REST_FRAMEWORK = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 12,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'AUTH_HEADER_TYPES': ('Bearer',),
}

CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:8080",
    "http://127.0.0.1:5173",
    "https://front-dls.vercel.app",
]

GOOGLE_CLIENT_ID = env('GOOGLE_CLIENT_ID')
GOOGLE_ADMIN_EMAILS = [
    e.strip().lower()
    for e in os.getenv('GOOGLE_ADMIN_EMAILS', '').split(',')
    if e.strip()
]

MERCADOPAGO_ACCESS_TOKEN = os.getenv('MERCADOPAGO_ACCESS_TOKEN', '')
MERCADOPAGO_PUBLIC_KEY = os.getenv('MERCADOPAGO_PUBLIC_KEY', '')

ASAAS_API_KEY = os.getenv('ASAAS_API_KEY', '')
ASAAS_WALLET_ID = os.getenv('ASAAS_WALLET_ID', '')
ASAAS_BASE_URL = os.getenv('ASAAS_BASE_URL', '')
FRONTEND_URL = os.getenv('FRONTEND_URL', 'https://front-dls.vercel.app')

# --- SuperFrete ---
SUPERFRETE_TOKEN = os.getenv('SUPERFRETE_TOKEN', '')
SUPERFRETE_BASE_URL = os.getenv('SUPERFRETE_BASE_URL', 'https://sandbox.superfrete.com')
SUPERFRETE_USER_AGENT = os.getenv('SUPERFRETE_USER_AGENT', 'DLS AutoPecas 1.0 (contato@dlsautopecas.com.br)')
SUPERFRETE_SERVICES = os.getenv('SUPERFRETE_SERVICES', '1,2,17')
SUPERFRETE_USE_INSURANCE = os.getenv('SUPERFRETE_USE_INSURANCE', 'True') == 'True'
SHIPPING_ORIGIN_POSTAL_CODE = os.getenv('SHIPPING_ORIGIN_POSTAL_CODE', '89210001')
LOJA_WHATSAPP = os.getenv('LOJA_WHATSAPP', '')