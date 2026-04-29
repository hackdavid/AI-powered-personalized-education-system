"""Role-aware dashboard router."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.db.models import Count


@login_required
def dashboard_router(request):
    """Route the authenticated user to their role-specific dashboard."""
    user = request.user

    # Django superuser -> superadmin dashboard (full technical access)
    if user.is_superuser:
        return render(request, 'dashboards/superadmin_dashboard.html', {'user': user})

    role = user.role_name

    if role == 'student':
        return render(request, 'dashboards/student_dashboard.html', {'user': user})

    if role == 'teacher':
        return render(request, 'dashboards/teacher_dashboard.html', {'user': user})

    if role == 'school_admin':
        from apps.service.models import Class
        from apps.accounts.models import User

        tenant = user.tenant
        ctx = {
            'user': user,
            'tenant': tenant,
            'stats': {
                'total_classes': Class.objects.filter(tenant=tenant, is_active=True).count(),
                'total_students': User.objects.filter(
                    tenant=tenant, role__name='student', is_active=True
                ).count(),
                'total_teachers': User.objects.filter(
                    tenant=tenant, role__name='teacher', is_active=True
                ).count(),
            },
        }
        return render(request, 'dashboards/school_admin_dashboard.html', ctx)

    if role == 'system_admin':
        return render(request, 'dashboards/system_admin_dashboard.html', {'user': user})

    return render(request, 'base/no_role.html', {'user': user})
