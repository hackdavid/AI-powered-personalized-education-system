import secrets
import string

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from apps.core.decorators import role_required
from apps.accounts.models import User, Role
from apps.web.forms import StudentInviteForm
from apps.service.models.academic import Class
from apps.service.models.enrollment import Enrollment


def _generate_password(length=10):
    chars = string.ascii_letters + string.digits + "!@#$%"
    return ''.join(secrets.choice(chars) for _ in range(length))


@login_required
@role_required(['school_admin'])
def student_list(request):
    students = User.objects.filter(
        tenant=request.tenant, role__name='student'
    ).select_related('role').prefetch_related('class_enrollments')

    # Build student data with enrollment info
    student_data = []
    for s in students:
        enrollment = s.class_enrollments.filter(is_active=True).select_related('class_obj').first()
        student_data.append({
            'student': s,
            'enrollment': enrollment,
        })

    form = StudentInviteForm(tenant=request.tenant)
    classes = Class.objects.filter(tenant=request.tenant, is_active=True)
    return render(request, 'school_admin/students/list.html', {
        'student_data': student_data,
        'students': students,
        'form': form,
        'classes': classes,
    })


@login_required
@role_required(['school_admin'])
def student_invite(request):
    credentials = None
    if request.method == 'POST':
        form = StudentInviteForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            email = form.cleaned_data['email']
            if User.objects.filter(email=email).exists():
                messages.error(request, f'A user with email "{email}" already exists.')
            else:
                student_role = Role.objects.get(name='student')
                # Use custom password if provided, otherwise auto-generate
                password = form.cleaned_data.get('password') or _generate_password()
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

                # Handle class enrollment if selected
                selected_class = form.cleaned_data.get('class_obj')
                enrollment_info = None
                if selected_class:
                    Enrollment.objects.create(
                        student=user,
                        class_obj=selected_class,
                        is_active=True
                    )
                    enrollment_info = selected_class.name
                    messages.success(
                        request,
                        f'Student "{user.get_full_name()}" created and enrolled in {selected_class.name}.'
                    )
                else:
                    messages.success(request, f'Student "{user.get_full_name()}" created.')

                credentials = {
                    'email': email,
                    'password': password,
                    'name': user.get_full_name(),
                    'class': enrollment_info,
                    'grade': user.grade_level,
                }
        else:
            for field, errs in form.errors.items():
                for e in errs:
                    messages.error(request, f'{field}: {e}')

    students = User.objects.filter(tenant=request.tenant, role__name='student').select_related('role').prefetch_related('class_enrollments')

    # Build student data with enrollment info
    student_data = []
    for s in students:
        enrollment = s.class_enrollments.filter(is_active=True).select_related('class_obj').first()
        student_data.append({
            'student': s,
            'enrollment': enrollment,
        })

    classes = Class.objects.filter(tenant=request.tenant, is_active=True)
    return render(request, 'school_admin/students/list.html', {
        'student_data': student_data,
        'students': students,
        'form': form if request.method == 'POST' else StudentInviteForm(tenant=request.tenant),
        'classes': classes,
        'credentials': credentials,
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

        # Handle enrollment
        class_id = request.POST.get('class_id')
        if class_id:
            try:
                selected_class = Class.objects.get(pk=int(class_id), tenant=request.tenant)
                # Deactivate all existing enrollments first
                Enrollment.objects.filter(student=student, is_active=True).update(is_active=False)
                # Create or reactivate enrollment in selected class
                enrollment, created = Enrollment.objects.get_or_create(
                    student=student,
                    class_obj=selected_class,
                    defaults={'is_active': True}
                )
                if not created:
                    enrollment.is_active = True
                    enrollment.save()
                messages.success(request, f'Student "{student.get_full_name()}" enrolled in {selected_class.name}.')
            except (Class.DoesNotExist, ValueError):
                messages.error(request, 'Invalid class selected.')

        student.save()
        return redirect('school_admin:student_list')

    # Get current enrollment
    current_enrollment = Enrollment.objects.filter(
        student=student, is_active=True
    ).select_related('class_obj').first()

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
        'form': form,
        'classes': classes,
        'edit_student': student,
        'current_enrollment': current_enrollment,
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
