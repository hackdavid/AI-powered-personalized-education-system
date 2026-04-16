"""
Development-specific settings.
"""

from .base import *

DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', '*.localhost']

# Database - Using SQLite for easier development setup
# Switch to PostgreSQL when ready
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# For PostgreSQL in development, uncomment below:
# DATABASES = {
#     'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': 'eduai_dev',
#         'USER': 'postgres',
#         'PASSWORD': 'postgres',
#         'HOST': 'localhost',
#         'PORT': '5432',
#     }
# }

# Add django-extensions for development
INSTALLED_APPS += [
    # 'debug_toolbar',  # Commented out - causes template errors
    'django_extensions',
]

# MIDDLEWARE += [
#     'debug_toolbar.middleware.DebugToolbarMiddleware',
# ]

# Debug toolbar configuration (commented out)
# INTERNAL_IPS = [
#     '127.0.0.1',
# ]

# Email backend for development
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Session security (relaxed for development)
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Cache (use dummy cache in development)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}
