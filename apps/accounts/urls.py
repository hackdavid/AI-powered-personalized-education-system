"""
Accounts app URL configuration
"""

from django.urls import path
from apps.accounts.views import auth_views

app_name = 'auth'

urlpatterns = [
    path('login/', auth_views.login_view, name='login'),
    path('logout/', auth_views.logout_view, name='logout'),
    path('password/change/', auth_views.password_change_view, name='password_change'),
    path('password/reset/', auth_views.password_reset_request_view, name='password_reset'),
]
