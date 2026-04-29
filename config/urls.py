"""Project URL configuration."""

from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from apps.web.urls import (
    auth_patterns,
    school_admin_patterns,
    public_patterns,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include((auth_patterns, 'auth'))),
    path('school-admin/', include((school_admin_patterns, 'school_admin'))),
    path('health/', include('apps.core.urls')),
    path('', include((public_patterns, 'web'))),
    # path('api/v1/', include('apps.service.api.urls', namespace='service_api')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
