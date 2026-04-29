from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction

from apps.core.decorators import role_required
from apps.accounts.models import User
from apps.service.models.academic import Class, ClassSubject, Subject
from apps.web.forms import ClassForm, ClassSubjectForm


# ── Helpers ───────────────────────────────────────────────

def _tenant_subjects(tenant):
    return Subject.objects.filter(tenant=tenant, is_active=True).order_by('name')


def _tenant_teachers(tenant):
    return User.objects.filter(
        tenant=tenant, role__name='teacher', is_active=True
    ).order_by('first_name', 'last_name')


def _apply_quick_assignments(cls, request):
    """
    Read paired POST lists `assignment_subject` + `assignment_teacher`
    and create ClassSubject rows. Idempotent: reuses any existing
    `(class, subject)` pair (which is unique). Returns count created.
    """
    subject_ids = request.POST.getlist('assignment_subject')
    teacher_ids = request.POST.getlist('assignment_teacher')
    created = 0
    for i, subject_id in enumerate(subject_ids):
        if not subject_id:
            continue
        subject = Subject.objects.filter(
            id=subject_id, tenant=cls.tenant, is_active=True
        ).first()
        if not subject:
            continue
        teacher_id = teacher_ids[i] if i < len(teacher_ids) else ''
        teacher = None
        if teacher_id:
            teacher = User.objects.filter(
                id=teacher_id, tenant=cls.tenant, role__name='teacher', is_active=True
            ).first()
        _, was_created = ClassSubject.objects.get_or_create(
            class_obj=cls,
            subject=subject,
            defaults={'teacher': teacher, 'is_active': True},
        )
        if was_created:
            created += 1
    return created


# ── Views ─────────────────────────────────────────────────

@login_required
@role_required(['school_admin'])
def class_list(request):
    classes = Class.objects.filter(
        tenant=request.tenant, is_active=True
    ).select_related('class_teacher').prefetch_related(
        'class_subjects__subject', 'class_subjects__teacher',
    )
    return render(request, 'school_admin/classes/list.html', {
        'classes': classes,
        'form': ClassForm(tenant=request.tenant),
        'class_subject_form': ClassSubjectForm(tenant=request.tenant),
        'subjects': _tenant_subjects(request.tenant),
        'teachers': _tenant_teachers(request.tenant),
    })


@login_required
@role_required(['school_admin'])
def class_create(request):
    if request.method == 'POST':
        form = ClassForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            with transaction.atomic():
                obj = form.save(commit=False)
                obj.tenant = request.tenant
                obj.save()
                created = _apply_quick_assignments(obj, request)
            if created:
                messages.success(
                    request,
                    f'Class "{obj.name}" created with {created} subject assignment{"s" if created != 1 else ""}.',
                )
            else:
                messages.success(request, f'Class "{obj.name}" created.')
        else:
            for field, errs in form.errors.items():
                for e in errs:
                    messages.error(request, f'{field}: {e}')
    return redirect('school_admin:class_list')


@login_required
@role_required(['school_admin'])
def class_edit(request, pk):
    obj = get_object_or_404(Class, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = ClassForm(request.POST, instance=obj, tenant=request.tenant)
        if form.is_valid():
            form.save()
            messages.success(request, f'Class "{obj.name}" updated.')
            return redirect('school_admin:class_list')
        for field, errs in form.errors.items():
            for e in errs:
                messages.error(request, f'{field}: {e}')
    return redirect('school_admin:class_list')


@login_required
@role_required(['school_admin'])
def class_delete(request, pk):
    obj = get_object_or_404(Class, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        obj.is_active = False
        obj.save()
        messages.success(request, f'Class "{obj.name}" deleted.')
    return redirect('school_admin:class_list')


@login_required
@role_required(['school_admin'])
def class_detail(request, pk):
    cls = get_object_or_404(Class, pk=pk, tenant=request.tenant)
    assignments = ClassSubject.objects.filter(
        class_obj=cls, is_active=True
    ).select_related('subject', 'teacher').order_by('subject__name')

    # Subjects already assigned to this class — used to grey them out in
    # the "Add assignment" picker so the admin doesn't try to re-add a
    # duplicate (would violate unique_together).
    assigned_subject_ids = set(assignments.values_list('subject_id', flat=True))

    return render(request, 'school_admin/classes/detail.html', {
        'class': cls,
        'assignments': assignments,
        'class_subject_form': ClassSubjectForm(tenant=request.tenant),
        'subjects': _tenant_subjects(request.tenant),
        'teachers': _tenant_teachers(request.tenant),
        'assigned_subject_ids': assigned_subject_ids,
    })


@login_required
@role_required(['school_admin'])
def assign_subject(request, pk):
    cls = get_object_or_404(Class, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = ClassSubjectForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            cs = form.save(commit=False)
            cs.class_obj = cls
            try:
                cs.save()
                messages.success(request, f'Assigned "{cs.subject.name}" to {cls.name}.')
            except Exception:
                messages.error(
                    request,
                    f'"{cs.subject.name}" is already assigned to {cls.name}. '
                    f'Use the teacher dropdown to change its teacher instead.',
                )
        else:
            for field, errs in form.errors.items():
                for e in errs:
                    messages.error(request, f'{field}: {e}')
    return redirect('school_admin:class_detail', pk=cls.pk)


@login_required
@role_required(['school_admin'])
def assignment_update(request, pk, csid):
    """Change the teacher on an existing ClassSubject assignment."""
    cls = get_object_or_404(Class, pk=pk, tenant=request.tenant)
    cs = get_object_or_404(ClassSubject, pk=csid, class_obj=cls)
    if request.method == 'POST':
        teacher_id = request.POST.get('teacher', '').strip()
        if teacher_id:
            teacher = User.objects.filter(
                id=teacher_id, tenant=request.tenant,
                role__name='teacher', is_active=True,
            ).first()
            if not teacher:
                messages.error(request, 'Invalid teacher selected.')
                return redirect('school_admin:class_detail', pk=pk)
            cs.teacher = teacher
        else:
            cs.teacher = None
        cs.save(update_fields=['teacher', 'updated_at'])
        teacher_label = cs.teacher.get_full_name() if cs.teacher else 'unassigned'
        messages.success(
            request,
            f'{cs.subject.name} → {teacher_label}.',
        )
    return redirect('school_admin:class_detail', pk=pk)


@login_required
@role_required(['school_admin'])
def remove_subject(request, pk, csid):
    cs = get_object_or_404(ClassSubject, pk=csid, class_obj__tenant=request.tenant)
    if request.method == 'POST':
        subject_name = cs.subject.name
        cs.delete()  # hard delete — easy to re-add via the picker
        messages.success(request, f'Removed "{subject_name}" from class.')
    return redirect('school_admin:class_detail', pk=pk)
