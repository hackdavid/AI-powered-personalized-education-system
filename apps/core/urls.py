"""
Core app URL configuration
"""

from django.urls import path
from apps.core import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard_router, name='dashboard'),
    path('health/', views.health_check, name='health_check'),
]
