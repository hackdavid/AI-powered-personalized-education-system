"""
Core views - Home, dashboard routing, and health checks
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils import timezone
from django.db import connection


def home(request):
    """Home page - redirect to dashboard if authenticated."""
    # if request.user.is_authenticated:
    #     return redirect('core:dashboard')
    return render(request, 'base/home.html')


@login_required
def dashboard_router(request):
    """
    Route users to role-specific dashboards.

    Note: Django superusers are redirected to superadmin dashboard.
    System admins (without superuser) get system_admin dashboard.
    """
    # Django Superuser gets special dashboard with Django admin access
    if request.user.is_superuser:
        return render(request, 'dashboards/superadmin_dashboard.html', {
            'user': request.user
        })

    # Check if user has a role assigned
    if not hasattr(request.user, 'role') or not request.user.role:
        return render(request, 'base/no_role.html', {
            'message': 'Your account does not have a role assigned. Please contact an administrator.'
        })

    role_name = request.user.role.name

    # Route based on role
    if role_name == 'student':
        return render(request, 'dashboards/student_dashboard.html', {
            'user': request.user,
            'tenant': request.tenant
        })
    elif role_name == 'teacher':
        return render(request, 'dashboards/teacher_dashboard.html', {
            'user': request.user,
            'tenant': request.tenant
        })
    elif role_name == 'school_admin':
        from apps.accounts.models import User
        from apps.common.models.academic import Class
        tenant = request.tenant
        return render(request, 'dashboards/school_admin_dashboard.html', {
            'user': request.user,
            'tenant': tenant,
            'total_users': User.objects.filter(tenant=tenant).count() if tenant else 0,
            'total_students': User.objects.filter(tenant=tenant, role__name='student').count() if tenant else 0,
            'total_teachers': User.objects.filter(tenant=tenant, role__name='teacher').count() if tenant else 0,
            'total_classes': Class.objects.filter(tenant=tenant, is_active=True).count() if tenant else 0,
        })
    elif role_name == 'system_admin':
        return render(request, 'dashboards/system_admin_dashboard.html', {
            'user': request.user
        })
    else:
        return render(request, 'base/no_role.html', {
            'message': f'Unknown role: {role_name}'
        })


def health_check(request):
    """
    Health check endpoint for monitoring.
    Returns status of critical services.
    """
    checks = {
        'database': _check_database(),
        'timestamp': timezone.now().isoformat(),
    }

    all_healthy = all(check['healthy'] for check in checks.values() if isinstance(check, dict))

    response_data = {
        'status': 'healthy' if all_healthy else 'unhealthy',
        'checks': checks,
    }

    status_code = 200 if all_healthy else 503
    return JsonResponse(response_data, status=status_code)


def _check_database():
    """Check database connectivity."""
    try:
        connection.ensure_connection()
        return {'healthy': True, 'message': 'Database connection OK'}
    except Exception as e:
        return {'healthy': False, 'message': f'Database error: {str(e)}'}
