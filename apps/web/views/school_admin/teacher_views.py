import secrets
import string

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from apps.core.decorators import role_required
from apps.accounts.models import User, Role
from apps.web.forms import TeacherInviteForm


def _generate_password(length=10):
    chars = string.ascii_letters + string.digits + "!@#$%"
    return ''.join(secrets.choice(chars) for _ in range(length))


def _teacher_queryset(tenant):
    """Teachers for a tenant, annotated with their workload."""
    return (
        User.objects
        .filter(tenant=tenant, role__name='teacher')
        .select_related('role')
        .annotate(
            assignment_count=Count(
                'taught_subjects',
                filter=Q(taught_subjects__is_active=True),
                distinct=True,
            ),
            class_count=Count(
                'taught_subjects__class_obj',
                filter=Q(taught_subjects__is_active=True),
                distinct=True,
            ),
        )
        .order_by('first_name', 'last_name')
    )


@login_required
@role_required(['school_admin'])
def teacher_list(request):
    teachers = _teacher_queryset(request.tenant)
    form = TeacherInviteForm()
    return render(request, 'school_admin/teachers/list.html', {
        'teachers': teachers, 'form': form,
    })


@login_required
@role_required(['school_admin'])
def teacher_invite(request):
    credentials = None
    if request.method == 'POST':
        form = TeacherInviteForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            if User.objects.filter(email=email).exists():
                messages.error(request, f'A user with email "{email}" already exists.')
            else:
                teacher_role = Role.objects.get(name='teacher')
                password = _generate_password()
                user = User.objects.create_user(
                    email=email,
                    password=password,
                    first_name=form.cleaned_data['first_name'],
                    last_name=form.cleaned_data['last_name'],
                    tenant=request.tenant,
                    role=teacher_role,
                    specialization=form.cleaned_data.get('specialization', ''),
                    employee_id=form.cleaned_data.get('employee_id', ''),
                    is_active=True,
                )
                messages.success(request, f'Teacher "{user.get_full_name()}" invited.')
                credentials = {'email': email, 'password': password, 'name': user.get_full_name()}
        else:
            for field, errs in form.errors.items():
                for e in errs:
                    messages.error(request, f'{field}: {e}')

    teachers = _teacher_queryset(request.tenant)
    return render(request, 'school_admin/teachers/list.html', {
        'teachers': teachers, 'form': form if request.method == 'POST' else TeacherInviteForm(),
        'credentials': credentials,
    })


@login_required
@role_required(['school_admin'])
def teacher_edit(request, pk):
    teacher = get_object_or_404(User, pk=pk, tenant=request.tenant, role__name='teacher')
    if request.method == 'POST':
        teacher.first_name = request.POST.get('first_name', teacher.first_name)
        teacher.last_name = request.POST.get('last_name', teacher.last_name)
        teacher.specialization = request.POST.get('specialization', teacher.specialization or '')
        teacher.employee_id = request.POST.get('employee_id', teacher.employee_id or '')
        teacher.save()
        messages.success(request, f'Teacher "{teacher.get_full_name()}" updated.')
        return redirect('school_admin:teacher_list')

    form = TeacherInviteForm(initial={
        'first_name': teacher.first_name,
        'last_name': teacher.last_name,
        'email': teacher.email,
        'specialization': teacher.specialization or '',
        'employee_id': teacher.employee_id or '',
    })
    return render(request, 'school_admin/teachers/list.html', {
        'teachers': _teacher_queryset(request.tenant),
        'form': form, 'edit_teacher': teacher,
    })


@login_required
@role_required(['school_admin'])
def teacher_toggle_active(request, pk):
    teacher = get_object_or_404(User, pk=pk, tenant=request.tenant, role__name='teacher')
    if request.method == 'POST':
        teacher.is_active = not teacher.is_active
        teacher.save()
        status = 'activated' if teacher.is_active else 'deactivated'
        messages.success(request, f'Teacher "{teacher.get_full_name()}" {status}.')
    return redirect('school_admin:teacher_list')
