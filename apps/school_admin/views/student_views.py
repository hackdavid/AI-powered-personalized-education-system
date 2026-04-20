import secrets
import string

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from apps.core.decorators import role_required
from apps.accounts.models import User, Role
from apps.school_admin.forms import StudentInviteForm
from apps.common.models.academic import Class


def _generate_password(length=10):
    chars = string.ascii_letters + string.digits + "!@#$%"
    return ''.join(secrets.choice(chars) for _ in range(length))


@login_required
@role_required(['school_admin'])
def student_list(request):
    students = User.objects.filter(
        tenant=request.tenant, role__name='student'
    ).select_related('role')
    form = StudentInviteForm()
    classes = Class.objects.filter(tenant=request.tenant, is_active=True)
    return render(request, 'school_admin/students/list.html', {
        'students': students, 'form': form, 'classes': classes,
    })


@login_required
@role_required(['school_admin'])
def student_invite(request):
    credentials = None
    if request.method == 'POST':
        form = StudentInviteForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            if User.objects.filter(email=email).exists():
                messages.error(request, f'A user with email "{email}" already exists.')
            else:
                student_role = Role.objects.get(name='student')
                password = _generate_password()
                user = User.objects.create_user(
                    email=email,
                    password=password,
                    first_name=form.cleaned_data['first_name'],
                    last_name=form.cleaned_data['last_name'],
                    tenant=request.tenant,
                    role=student_role,
                    grade_level=form.cleaned_data.get('grade_level'),
                    student_id=form.cleaned_data.get('student_id', ''),
                    is_active=True,
                )
                messages.success(request, f'Student "{user.get_full_name()}" invited.')
                credentials = {'email': email, 'password': password, 'name': user.get_full_name()}
        else:
            for field, errs in form.errors.items():
                for e in errs:
                    messages.error(request, f'{field}: {e}')

    students = User.objects.filter(tenant=request.tenant, role__name='student').select_related('role')
    classes = Class.objects.filter(tenant=request.tenant, is_active=True)
    return render(request, 'school_admin/students/list.html', {
        'students': students,
        'form': form if request.method == 'POST' else StudentInviteForm(),
        'classes': classes, 'credentials': credentials,
    })


@login_required
@role_required(['school_admin'])
def student_edit(request, pk):
    student = get_object_or_404(User, pk=pk, tenant=request.tenant, role__name='student')
    if request.method == 'POST':
        student.first_name = request.POST.get('first_name', student.first_name)
        student.last_name = request.POST.get('last_name', student.last_name)
        student.student_id = request.POST.get('student_id', student.student_id or '')
        grade = request.POST.get('grade_level')
        if grade:
            student.grade_level = int(grade)
        student.save()
        messages.success(request, f'Student "{student.get_full_name()}" updated.')
        return redirect('school_admin:student_list')

    form = StudentInviteForm(initial={
        'first_name': student.first_name,
        'last_name': student.last_name,
        'email': student.email,
        'grade_level': student.grade_level,
        'student_id': student.student_id or '',
    })
    classes = Class.objects.filter(tenant=request.tenant, is_active=True)
    return render(request, 'school_admin/students/list.html', {
        'students': User.objects.filter(tenant=request.tenant, role__name='student'),
        'form': form, 'classes': classes, 'edit_student': student,
    })


@login_required
@role_required(['school_admin'])
def student_toggle_active(request, pk):
    student = get_object_or_404(User, pk=pk, tenant=request.tenant, role__name='student')
    if request.method == 'POST':
        student.is_active = not student.is_active
        student.save()
        status = 'activated' if student.is_active else 'deactivated'
        messages.success(request, f'Student "{student.get_full_name()}" {status}.')
    return redirect('school_admin:student_list')
