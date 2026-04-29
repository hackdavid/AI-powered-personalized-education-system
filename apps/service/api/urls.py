"""URL routes for `apps.service.api`. Mounted at `/api/v1/` in `config.urls`."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .tutoring import TutoringSessionViewSet

router = DefaultRouter()
router.register(r'tutoring/sessions', TutoringSessionViewSet, basename='tutoring-session')

app_name = 'service_api'

urlpatterns = [
    path('', include(router.urls)),
]
