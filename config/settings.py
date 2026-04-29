"""
Django settings for the EduAI platform.

Single-file config that toggles dev / prod behaviour via env vars instead
of separate settings modules. Everything is driven by `DJANGO_DEBUG` and
a handful of optional URLs (`DATABASE_URL`, `REDIS_URL`, `SENTRY_DSN`,
`EMBEDDER_API_URL`, ...), so one pip install and one `.env` file works
for local dev, CI, and production hosts.

Env var quick reference (full list in `.env.example`):

  * DJANGO_SECRET_KEY     (required in prod)
  * DJANGO_DEBUG          (bool; default False)
  * DJANGO_ALLOWED_HOSTS  (csv; default localhost,127.0.0.1)
  * DATABASE_URL          (postgres URL; required when DEBUG=False)
  * REDIS_URL             (optional; enables Redis cache when DEBUG=False)
  * SENTRY_DSN            (optional; enables Sentry when DEBUG=False)
  * EMBEDDER_API_URL, EMBEDDER_API_KEY, EMBEDDING_PROVIDER
  * OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL_NAME
  * EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD
"""

from pathlib import Path

from decouple import config
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Core flags
# ---------------------------------------------------------------------------

SECRET_KEY = config('DJANGO_SECRET_KEY', default='django-insecure-change-this-in-production')
DEBUG = config('DJANGO_DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('DJANGO_ALLOWED_HOSTS', default='localhost,127.0.0.1').split(',')

# Render injects RENDER_EXTERNAL_HOSTNAME (e.g. `eduai-platform.onrender.com`)
# at runtime. Adding it here means a fresh deploy works without anyone
# having to remember to put it in DJANGO_ALLOWED_HOSTS.
_render_host = config('RENDER_EXTERNAL_HOSTNAME', default='')
if _render_host and _render_host not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_render_host)


# ---------------------------------------------------------------------------
# Apps & middleware
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party
    'rest_framework',
    'corsheaders',
    'django_filters',

    # First-party (4-app layout)
    'apps.core',         # infrastructure: base models, middleware, decorators
    'apps.accounts',     # identity: User, Role, Permission, Tenant + auth
    'apps.service',      # domain: models + business services + REST APIs
    'apps.web',          # presentation: HTML views, dashboards, forms
]

if DEBUG:
    # Only useful in dev (shell_plus, graph_models, runserver_plus, ...)
    INSTALLED_APPS.append('django_extensions')

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    # Custom
    'apps.core.middleware.tenant_middleware.TenantMiddleware',
    'apps.core.middleware.request_logging.RequestLoggingMiddleware',
    'apps.core.middleware.exception_handler.ExceptionHandlerMiddleware',
]

if not DEBUG:
    # WhiteNoise serves static files in prod without needing nginx / cloudfront.
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'frontend' / 'templates'],
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


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
#
# Resolution order:
#   1. DATABASE_URL (Supabase / Postgres / any compatible) — always wins.
#   2. DEBUG=True and no DATABASE_URL → SQLite at BASE_DIR/db.sqlite3.
#   3. Otherwise fail fast (prod must set DATABASE_URL).

DATABASE_URL = config('DATABASE_URL', default='')

if DATABASE_URL:
    import dj_database_url
    # conn_max_age=0 -> close the underlying socket at the end of every
    # request. Important when DATABASE_URL points at a transaction-mode
    # pooler (Supabase port 6543): the pooler hands back a different
    # physical connection per transaction, so keeping one open wastes a
    # pool slot and quickly trips the free-tier `EMAXCONNSESSION` limit.
    #
    # DISABLE_SERVER_SIDE_CURSORS=True is also required for transaction
    # pooling — server-side cursors don't survive the pool boundary.
    DATABASES = {
        'default': dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=0,
            conn_health_checks=True,
            disable_server_side_cursors=True,
        ),
    }
elif DEBUG:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }
else:
    raise ImproperlyConfigured(
        'DATABASE_URL is required when DJANGO_DEBUG is False. '
        'Set it in your environment or .env file.'
    )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

AUTH_USER_MODEL = 'accounts.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = '/auth/login/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/auth/login/'


# ---------------------------------------------------------------------------
# i18n / static / media
# ---------------------------------------------------------------------------

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'frontend' / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

if not DEBUG:
    STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


# ---------------------------------------------------------------------------
# REST / CORS
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default='http://localhost:3000').split(',')
CORS_ALLOW_CREDENTIALS = True


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG


# ---------------------------------------------------------------------------
# Production-only security headers
# ---------------------------------------------------------------------------

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    # Render (and most PaaS load balancers) terminate TLS in front of
    # our container and forward `X-Forwarded-Proto: https`. Trusting it
    # means SECURE_SSL_REDIRECT doesn't loop on already-HTTPS traffic.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = 'DENY'


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
#
# Dev: dummy (no caching, helps avoid stale-data confusion).
# Prod with REDIS_URL set: Redis.
# Prod without REDIS_URL: in-process locmem (fine for single-worker).

if DEBUG:
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}}
elif config('REDIS_URL', default=''):
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': config('REDIS_URL'),
        }
    }
else:
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

if DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
    EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
    EMAIL_USE_TLS = True
    EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
    EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
    DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@eduai.com')


# ---------------------------------------------------------------------------
# Sentry (prod only, opt-in via SENTRY_DSN)
# ---------------------------------------------------------------------------

if not DEBUG and config('SENTRY_DSN', default=''):
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    sentry_sdk.init(
        dsn=config('SENTRY_DSN'),
        integrations=[DjangoIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
    )


# ---------------------------------------------------------------------------
# AI providers — the default values are overridden at runtime by the
# `AppSetting` table (see `apps.core.apps.CoreConfig.ready()` and
# `docs/memory.md` §14). Values here act as the `.env` fallback.
# ---------------------------------------------------------------------------

OPENAI_API_KEY = config('OPENAI_API_KEY', default='')
OPENAI_BASE_URL = config('OPENAI_BASE_URL', default='https://api.openai.com/v1')
OPENAI_MODEL_NAME = config('OPENAI_MODEL_NAME', default='gpt-4')
ANTHROPIC_API_KEY = config('ANTHROPIC_API_KEY', default='')
LLM_PROVIDER = config('LLM_PROVIDER', default='openai')

# Embedding provider: 'remote' (HuggingFace Space, no local torch) or 'local'
# (sentence-transformers in-process). Default is remote so a fresh
# `pip install -r requirements.txt` works on any OS without torch.
EMBEDDING_PROVIDER = config('EMBEDDING_PROVIDER', default='remote').lower()
EMBEDDER_API_URL = config('EMBEDDER_API_URL', default='')
EMBEDDER_API_KEY = config('EMBEDDER_API_KEY', default='')
EMBEDDING_MODEL_NAME = config('EMBEDDING_MODEL_NAME', default='all-MiniLM-L6-v2')
EMBEDDING_MODEL_PRELOAD = config('EMBEDDING_MODEL_PRELOAD', default=False, cast=bool)

# Vector store identifier. Currently only 'pgvector' is supported; kept
# as a setting so a future Pinecone / Weaviate backend could plug in
# via the same VectorStoreClient facade.
VECTOR_STORE_TYPE = config('VECTOR_STORE_TYPE', default='pgvector')


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_log_file = (
    Path(config('LOG_FILE')) if config('LOG_FILE', default='')
    else BASE_DIR / 'logs' / 'app.log'
)
_log_file.parent.mkdir(parents=True, exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%(asctime)s %(name)s %(levelname)s %(message)s',
        },
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(_log_file),
            'maxBytes': 1024 * 1024 * 10,
            'backupCount': 5,
            'formatter': 'json',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'WARNING' if not DEBUG else 'INFO',
        },
        'apps': {
            'handlers': ['console', 'file'],
            'level': 'INFO' if not DEBUG else 'DEBUG',
        },
    },
}
