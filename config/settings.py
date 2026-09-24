import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables natively if .env exists
env_path = BASE_DIR / '.env'
if env_path.exists():
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'").strip('"'))

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-dev-key-change-in-production')
DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 't')

ALLOWED_HOSTS = [host.strip() for host in os.getenv('ALLOWED_HOSTS', '*').split(',') if host.strip()]
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.getenv('CSRF_TRUSTED_ORIGINS', 'http://127.0.0.1,http://localhost').split(',') if origin.strip()]

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party apps
    'rest_framework',

    # Internal Business Apps
    'apps.core.apps.CoreConfig',
    'apps.users.apps.UsersConfig',
    'apps.wallet.apps.WalletConfig',
    'apps.payments.apps.PaymentsConfig',
    'apps.catalog.apps.CatalogConfig',
    'apps.inventory.apps.InventoryConfig',
    'apps.orders.apps.OrdersConfig',
    'apps.fulfillment.apps.FulfillmentConfig',
    'apps.providers.apps.ProvidersConfig',
    'apps.services_app.apps.ServicesAppConfig',
    'apps.notifications.apps.NotificationsConfig',
    'apps.audit.apps.AuditConfig',
    'apps.telegram_bot.apps.TelegramBotConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Database Configuration
DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
USE_POSTGRES = os.getenv('USE_POSTGRES', 'False').lower() in ('true', '1', 't') or bool(DATABASE_URL)

if DATABASE_URL:
    import urllib.parse
    parsed_url = urllib.parse.urlparse(DATABASE_URL)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    ssl_mode = query_params.get('sslmode', ['require'])[0]

    raw_user = urllib.parse.unquote(parsed_url.username or '')
    hostname = parsed_url.hostname or ''
    db_options = {'sslmode': ssl_mode}

    # Neon Cloud options
    if 'neon.tech' in hostname:
        endpoint_id = hostname.split('.')[0].replace('-pooler', '')
        db_options['options'] = f'endpoint={endpoint_id}'

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': parsed_url.path.lstrip('/') or 'neondb',
            'USER': raw_user,
            'PASSWORD': urllib.parse.unquote(parsed_url.password or ''),
            'HOST': hostname,
            'PORT': parsed_url.port or 5432,
            'OPTIONS': db_options,
            'CONN_MAX_AGE': 600,
            'CONN_HEALTH_CHECKS': True,
        }
    }
elif USE_POSTGRES:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME', 'tele_bot_db'),
            'USER': os.getenv('DB_USER', 'postgres'),
            'PASSWORD': os.getenv('DB_PASSWORD', 'postgres'),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'ar'
TIME_ZONE = 'Asia/Aden'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
}

# ==============================================================================
# Celery Configuration
# ==============================================================================
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://127.0.0.1:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# ==============================================================================
# Telegram Configuration
# ==============================================================================
CUSTOMER_BOT_TOKEN = os.getenv('CUSTOMER_BOT_TOKEN', '')
ADMIN_BOT_TOKEN = os.getenv('ADMIN_BOT_TOKEN', '')
ADMIN_GROUP_ID = os.getenv('ADMIN_GROUP_ID', '')
SUCCESS_CHANNEL_ID = os.getenv('SUCCESS_CHANNEL_ID', '').strip()
SUCCESS_CHANNEL_URL = os.getenv('SUCCESS_CHANNEL_URL', '').strip()
SUCCESS_CHANNEL_TITLE = os.getenv('SUCCESS_CHANNEL_TITLE', 'قناة التفعيلات المباشرة').strip()
SUPER_ADMIN_TELEGRAM_ID = int(os.getenv('SUPER_ADMIN_TELEGRAM_ID', '0')) if os.getenv('SUPER_ADMIN_TELEGRAM_ID', '0').isdigit() else 0
REQUIRED_CHANNEL_ID = os.getenv('REQUIRED_CHANNEL_ID', '').strip()
REQUIRED_CHANNEL_URL = os.getenv('REQUIRED_CHANNEL_URL', '').strip()
REQUIRED_CHANNEL_TITLE = os.getenv('REQUIRED_CHANNEL_TITLE', 'قناة المتجر الرسمية').strip()

# ==============================================================================
# Security & Encryption Key (Fernet 32-byte key)
# ==============================================================================
DATA_ENCRYPTION_KEY = os.getenv('DATA_ENCRYPTION_KEY', '')

# ==============================================================================
# Cloudinary Configuration
# ==============================================================================
CLOUDINARY_CLOUD_NAME = os.getenv('CLOUDINARY_CLOUD_NAME', '')
CLOUDINARY_API_KEY = os.getenv('CLOUDINARY_API_KEY', '')
CLOUDINARY_API_SECRET = os.getenv('CLOUDINARY_API_SECRET', '')

# ==============================================================================
# Currency & Pricing Defaults
# ==============================================================================
DEFAULT_EXCHANGE_RATE_USD_TO_YER = float(os.getenv('DEFAULT_EXCHANGE_RATE_USD_TO_YER', '550.00'))
BASE_CURRENCY = os.getenv('BASE_CURRENCY', 'YER')
