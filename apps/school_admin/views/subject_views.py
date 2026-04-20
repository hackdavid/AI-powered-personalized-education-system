from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from apps.core.decorators import role_required
from apps.common.models.academic import Subject
from apps.school_admin.forms import SubjectForm


@login_required
@role_required(['school_admin'])
def subject_list(request):
    subjects = Subject.objects.filter(tenant=request.tenant, is_active=True)
    form = SubjectForm()
    return render(request, 'school_admin/subjects/list.html', {
        'subjects': subjects, 'form': form,
    })


@login_required
@role_required(['school_admin'])
def subject_create(request):
    if request.method == 'POST':
        form = SubjectForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.save()
            messages.success(request, f'Subject "{obj.name}" created.')
        else:
            for field, errs in form.errors.items():
                for e in errs:
                    messages.error(request, f'{field}: {e}')
    return redirect('school_admin:subject_list')


@login_required
@role_required(['school_admin'])
def subject_edit(request, pk):
    obj = get_object_or_404(Subject, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        form = SubjectForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, f'Subject "{obj.name}" updated.')
            return redirect('school_admin:subject_list')
        else:
            for field, errs in form.errors.items():
                for e in errs:
                    messages.error(request, f'{field}: {e}')
            return redirect('school_admin:subject_list')
    return redirect('school_admin:subject_list')


@login_required
@role_required(['school_admin'])
def subject_delete(request, pk):
    obj = get_object_or_404(Subject, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        obj.is_active = False
        obj.save()
        messages.success(request, f'Subject "{obj.name}" deleted.')
    return redirect('school_admin:subject_list')
