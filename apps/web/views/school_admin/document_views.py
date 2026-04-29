from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from apps.core.decorators import role_required
from apps.service.models.document import Document
from apps.web.forms import DocumentUploadForm


@login_required
@role_required(['school_admin'])
def document_list(request):
    docs = Document.objects.filter(tenant=request.tenant).select_related('subject', 'class_obj')
    form = DocumentUploadForm(tenant=request.tenant)
    return render(request, 'school_admin/documents/list.html', {
        'documents': docs, 'form': form,
    })


@login_required
@role_required(['school_admin'])
def document_upload(request):
    if request.method == 'POST':
        form = DocumentUploadForm(request.POST, request.FILES, tenant=request.tenant)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.tenant = request.tenant
            obj.created_by = request.user
            obj.updated_by = request.user
            obj.save()
            messages.success(request, f'"{obj.title}" uploaded successfully.')
        else:
            for field, errs in form.errors.items():
                for e in errs:
                    messages.error(request, f'{field}: {e}')
    return redirect('school_admin:document_list')


@login_required
@role_required(['school_admin'])
def document_delete(request, pk):
    doc = get_object_or_404(Document, pk=pk, tenant=request.tenant)
    if request.method == 'POST':
        title = doc.title
        doc.file.delete(save=False)
        doc.delete()
        messages.success(request, f'"{title}" deleted.')
    return redirect('school_admin:document_list')
