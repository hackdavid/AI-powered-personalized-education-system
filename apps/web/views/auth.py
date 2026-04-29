"""
Authentication views - Login, logout, password management.
"""

from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_protect
from apps.accounts.services.auth_service import AuthService
from apps.core.utils.response import APIResponse


@require_http_methods(["GET", "POST"])
@csrf_protect
def login_view(request):
    """User login view."""
    # Redirect if already authenticated
    if request.user.is_authenticated:
        return redirect('web:dashboard')

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        remember_me = request.POST.get('remember_me') == 'on'

        # Validate inputs
        if not email or not password:
            messages.error(request, "Email and password are required")
            return render(request, 'auth/login.html')

        # Attempt login
        success, user, message = AuthService.login_user(request, email, password, remember_me)

        if success:
            messages.success(request, f"Welcome back, {user.get_full_name()}!")
            # Redirect to next or dashboard
            next_url = request.GET.get('next', 'web:dashboard')
            return redirect(next_url)
        else:
            messages.error(request, message)

    return render(request, 'auth/login.html')


@require_http_methods(["GET", "POST"])
def logout_view(request):
    """User logout view."""
    if request.user.is_authenticated:
        AuthService.logout_user(request)
        messages.success(request, "You have been logged out successfully")

    return redirect('auth:login')


@require_http_methods(["GET", "POST"])
@csrf_protect
def password_change_view(request):
    """Password change view."""
    if not request.user.is_authenticated:
        return redirect('auth:login')

    if request.method == 'POST':
        old_password = request.POST.get('old_password', '')
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')

        # Validate inputs
        if not old_password or not new_password or not confirm_password:
            messages.error(request, "All fields are required")
            return render(request, 'auth/password_change.html')

        if new_password != confirm_password:
            messages.error(request, "New passwords do not match")
            return render(request, 'auth/password_change.html')

        if len(new_password) < 8:
            messages.error(request, "Password must be at least 8 characters long")
            return render(request, 'auth/password_change.html')

        # Change password
        success, message = AuthService.change_password(request.user, old_password, new_password)

        if success:
            messages.success(request, message)
            return redirect('web:dashboard')
        else:
            messages.error(request, message)

    return render(request, 'auth/password_change.html')


@require_http_methods(["GET", "POST"])
@csrf_protect
def password_reset_request_view(request):
    """Password reset request view."""
    if request.user.is_authenticated:
        return redirect('web:dashboard')

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()

        if not email:
            messages.error(request, "Email is required")
            return render(request, 'auth/password_reset_request.html')

        # Initiate password reset
        success, token, uid, message = AuthService.initiate_password_reset(email)

        # Always show success message (don't reveal if email exists)
        messages.success(request, "If an account exists with this email, you will receive password reset instructions")
        return redirect('auth:login')

    return render(request, 'auth/password_reset_request.html')
