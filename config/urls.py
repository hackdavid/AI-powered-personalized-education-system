"""
EduAI Platform URL Configuration
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include('apps.accounts.urls', namespace='auth')),

    # Role-based dashboard routes
    path('', include('apps.core.urls', namespace='core')),

    # Feature app routes (to be added as features are implemented)
    # path('student/', include('apps.student_portal.urls', namespace='student')),
    # path('teacher/', include('apps.teacher_portal.urls', namespace='teacher')),
    # path('school-admin/', include('apps.school_admin.urls', namespace='school_admin')),
    # path('api/v1/', include('apps.api.urls', namespace='api')),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

    # Debug toolbar (commented out)
    # if 'debug_toolbar' in settings.INSTALLED_APPS:
    #     import debug_toolbar
    #     urlpatterns += [
    #         path('__debug__/', include(debug_toolbar.urls)),
    #     ]

# Customize admin site
admin.site.site_header = "EduAI Platform Administration"
admin.site.site_title = "EduAI Admin"
admin.site.index_title = "Welcome to EduAI Platform Administration"
