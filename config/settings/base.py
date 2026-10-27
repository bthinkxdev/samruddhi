"""
Base Django settings shared across all environments for config.
"""

from pathlib import Path
from celery.schedules import crontab

import environ

env = environ.Env(
    DEBUG=(bool, False),
    USE_S3=(bool, False),
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent

environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="django-insecure-dev-only-change-in-production")

DEBUG = env.bool("DEBUG", default=False)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

LOCAL_APPS = [
    "core",
    "accounts",
    "catalog",
    "cart",
    "checkout",
    "orders",
    "payments",
    "delivery",
    "recurring",
    "marketing",
    "cms",
    "notifications",
    "reports",
    "dashboard",
    "whatsapp",
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
] + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.i18n",
                "django.template.context_processors.csrf",
                "core.context_processors.storefront",
                "dashboard.context_processors.dashboard_chrome",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

_database_url = env(
    "DATABASE_URL",
    default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
)

if _database_url.startswith("sqlite"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {"default": env.db("DATABASE_URL")}
    # The psycopg pool below manages connection lifetime itself; Django raises
    # ImproperlyConfigured if CONN_MAX_AGE is also set to a persistent value.
    DATABASES["default"]["CONN_MAX_AGE"] = 0
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
    DATABASES["default"]["OPTIONS"] = {
        "connect_timeout": env.int("DB_CONNECT_TIMEOUT", default=10),
        "options": env(
            "DB_STATEMENT_TIMEOUT_OPTIONS",
            default="-c statement_timeout=30000",
        ),
        "pool": {
            "min_size": env.int("DB_POOL_MIN_SIZE", default=2),
            "max_size": env.int("DB_POOL_MAX_SIZE", default=10),
        },
    }

REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/1")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/2")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Asia/Kolkata"
CELERY_BEAT_SCHEDULE = {
    "celery-health-check-every-minute": {
        "task": "core.tasks.celery_health_check",
        "schedule": 60.0,
    },

    "process-due-recurring-schedules-daily": {
        "task": "recurring.tasks.process_due_schedules",
        "schedule": crontab(hour=0, minute=30),
    },

    "aggregate-daily-reports-nightly": {
        "task": "reports.tasks.aggregate_daily_reports",
        "schedule": crontab(hour=0, minute=10),
    },

    "scan-abandoned-carts-hourly": {
        "task": "marketing.tasks.scan_abandoned_carts",
        "schedule": 3600.0,
    },

    "refresh-sitemap-daily": {
        "task": "core.tasks.refresh_sitemap_cache",
        "schedule": crontab(hour=0, minute=45),
    },
}

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

USE_S3 = env.bool("USE_S3", default=False)

if USE_S3:
    AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="me-south-1")
    AWS_S3_CUSTOM_DOMAIN = env("AWS_S3_CUSTOM_DOMAIN", default=None)
    AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=86400"}
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = False
    AWS_S3_FILE_OVERWRITE = False

    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
    if AWS_S3_CUSTOM_DOMAIN:
        MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/media/"
    else:
        MEDIA_URL = (
            f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}" ".amazonaws.com/media/"
        )

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "/accounts/login/email-otp/"
LOGIN_REDIRECT_URL = "/accounts/dashboard/"

GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID", default="")

ACCOUNTS_OTP_EXPIRY_SECONDS = env.int("ACCOUNTS_OTP_EXPIRY_SECONDS", default=300)
ACCOUNTS_OTP_MAX_ATTEMPTS = env.int("ACCOUNTS_OTP_MAX_ATTEMPTS", default=5)
ACCOUNTS_GUEST_TOKEN_MAX_AGE = env.int("ACCOUNTS_GUEST_TOKEN_MAX_AGE", default=86400)

LANGUAGE_CODE = "en"

LANGUAGES = [
    ("en", "English"),
]

LOCALE_PATHS = [BASE_DIR / "locale"]

TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_L10N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

from django.contrib.messages import constants as _message_constants  # noqa: E402

MESSAGE_TAGS = {_message_constants.ERROR: "danger"}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}

#SMTP email settings
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=25)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=False)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="desertmobiles@gmail.com")

SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin-allow-popups"

#razorpay webhook — separate from the razorpay_key_id/secret stored on SiteSettings,
#this is deployment-only config for verifying payments.views.razorpay_webhook_view
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET", default="")

#meta pixel — empty META_PIXEL_ID disables every browser event; the Conversions API
#(server-side Purchase) additionally needs META_CAPI_ACCESS_TOKEN. See core/meta_pixel.py.
META_PIXEL_ID = env("META_PIXEL_ID", default="").strip()
META_CAPI_ACCESS_TOKEN = env("META_CAPI_ACCESS_TOKEN", default="").strip()
META_TEST_EVENT_CODE = env("META_TEST_EVENT_CODE", default="").strip()
META_API_VERSION = env("META_API_VERSION", default="v21.0")


#whatsapp (Gupshup WhatsApp Business API) — see whatsapp/.
#WHATSAPP_ENABLED is the master switch for automatic order messages (off by default).
WHATSAPP_ENABLED = env.bool("WHATSAPP_ENABLED", default=False)
GUPSHUP_API_KEY = env("GUPSHUP_API_KEY", default="").strip()
GUPSHUP_SOURCE_NUMBER = env("GUPSHUP_SOURCE_NUMBER", default="").strip()
GUPSHUP_APP_NAME = env("GUPSHUP_APP_NAME", default="").strip()
GUPSHUP_WEBHOOK_SECRET = env("GUPSHUP_WEBHOOK_SECRET", default="").strip()
WHATSAPP_DEFAULT_COUNTRY_CODE = env("WHATSAPP_DEFAULT_COUNTRY_CODE", default="91")
WHATSAPP_REQUEST_TIMEOUT = env.int("WHATSAPP_REQUEST_TIMEOUT", default=10)
