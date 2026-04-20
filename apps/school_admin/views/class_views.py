import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from apps.core.decorators import role_required
from apps.common.models.academic import Class, ClassSubject
from apps.school_admin.forms import ClassForm, ClassSubjectForm
from apps.core.utils.response import APIResponse


@login_required
@role_required(['school_admin'])
def class_list(request):
    classes = Class.objects.filter(
        tenant=request.tenant, is_active=True
    ).select_related('class_teacher').prefetch_related('class_subjects')
    form = ClassForm(tenant=request.tenant)
    class_subject_form = ClassSubjectForm(tenant=request.tenant)
    return render(request, 'school_admin/classes/list.html', {
        'classes': classes, 'form': form, 'class_subject_form': class_subject_form,
    })


@login_required
@role_required(['school_admin'])
def class_create(request):
    if request.method == 'POST':
        form = ClassForm(request.POST, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
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
        else:
            for field, errs in form.errors.items():
                for e in errs:
                    messages.error(request, f'{field}: {e}')
            return redirect('school_admin:class_list')
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
    ).select_related('subject', 'teacher')
    class_subject_form = ClassSubjectForm(tenant=request.tenant)
    return render(request, 'school_admin/classes/detail.html', {
        'class': cls, 'assignments': assignments, 'class_subject_form': class_subject_form,
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
            cs.save()
            messages.success(request, f'Subject "{cs.subject.name}" assigned to {cls.name}.')
        else:
            for field, errs in form.errors.items():
                for e in errs:
                    messages.error(request, f'{field}: {e}')
    return redirect('school_admin:class_detail', pk=cls.pk)


@login_required
@role_required(['school_admin'])
def remove_subject(request, pk, csid):
    cs = get_object_or_404(ClassSubject, pk=csid, class_obj__tenant=request.tenant)
    if request.method == 'POST':
        cs.is_active = False
        cs.save()
        messages.success(request, f'Removed "{cs.subject.name}" from class.')
    return redirect('school_admin:class_detail', pk=pk)
