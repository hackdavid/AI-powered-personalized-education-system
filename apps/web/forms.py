from django import forms
from apps.service.models.academic import Class, Subject, ClassSubject
from apps.service.models.document import Document
from apps.accounts.models import User


# ── Classes ──────────────────────────────────────────────

class ClassForm(forms.ModelForm):
    class Meta:
        model = Class
        fields = ['name', 'grade_level', 'section', 'academic_year', 'class_teacher', 'max_students']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Grade 8 - Section A'}),
            'grade_level': forms.NumberInput(attrs={'class': 'form-input', 'min': 1, 'max': 12}),
            'section': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'A'}),
            'academic_year': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. 2025-2026'}),
            'max_students': forms.NumberInput(attrs={'class': 'form-input', 'min': 1}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['class_teacher'].queryset = User.objects.filter(
                tenant=tenant, role__name='teacher', is_active=True
            )
        self.fields['class_teacher'].required = False
        self.fields['class_teacher'].widget.attrs.update({'class': 'form-input'})


# ── Subjects ─────────────────────────────────────────────

class SubjectForm(forms.ModelForm):
    class Meta:
        model = Subject
        fields = ['name', 'code', 'description', 'color']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. Mathematics'}),
            'code': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'e.g. MATH'}),
            'description': forms.Textarea(attrs={'class': 'form-input', 'rows': 3}),
            'color': forms.TextInput(attrs={'class': 'form-input', 'type': 'color'}),
        }


# ── Class-Subject Assignment ─────────────────────────────

class ClassSubjectForm(forms.ModelForm):
    class Meta:
        model = ClassSubject
        fields = ['subject', 'teacher']
        widgets = {
            'subject': forms.Select(attrs={'class': 'form-input'}),
            'teacher': forms.Select(attrs={'class': 'form-input'}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['subject'].queryset = Subject.objects.filter(tenant=tenant, is_active=True)
            self.fields['teacher'].queryset = User.objects.filter(
                tenant=tenant, role__name='teacher', is_active=True
            )
        self.fields['teacher'].required = False


# ── Teacher Invite ───────────────────────────────────────

class TeacherInviteForm(forms.Form):
    first_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={
        'class': 'form-input', 'placeholder': 'First name'
    }))
    last_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={
        'class': 'form-input', 'placeholder': 'Last name'
    }))
    email = forms.EmailField(widget=forms.EmailInput(attrs={
        'class': 'form-input', 'placeholder': 'teacher@school.com'
    }))
    specialization = forms.CharField(max_length=100, required=False, widget=forms.TextInput(attrs={
        'class': 'form-input', 'placeholder': 'e.g. Mathematics, Physics'
    }))
    employee_id = forms.CharField(max_length=50, required=False, widget=forms.TextInput(attrs={
        'class': 'form-input', 'placeholder': 'Employee ID'
    }))


# ── Student Invite ───────────────────────────────────────

class StudentInviteForm(forms.Form):
    first_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={
        'class': 'form-input', 'placeholder': 'First name'
    }))
    last_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={
        'class': 'form-input', 'placeholder': 'Last name'
    }))
    email = forms.EmailField(widget=forms.EmailInput(attrs={
        'class': 'form-input', 'placeholder': 'student@school.com'
    }))
    grade_level = forms.IntegerField(widget=forms.NumberInput(attrs={
        'class': 'form-input', 'min': 1, 'max': 12
    }))
    student_id = forms.CharField(max_length=50, required=False, widget=forms.TextInput(attrs={
        'class': 'form-input', 'placeholder': 'Student ID'
    }))
    class_obj = forms.ModelChoiceField(
        queryset=Class.objects.none(),
        required=False,
        widget=forms.Select(attrs={'class': 'form-input'}),
        label='Enroll in Class',
        help_text='Assign student to a class (optional)'
    )
    password = forms.CharField(
        max_length=128,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Leave blank to auto-generate'
        }),
        help_text='Leave blank to auto-generate a secure password'
    )

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['class_obj'].queryset = Class.objects.filter(
                tenant=tenant, is_active=True
            ).order_by('grade_level', 'section')


# ── Document Upload ──────────────────────────────────────

class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['title', 'file', 'subject', 'class_obj', 'description']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Book / document title'}),
            'description': forms.Textarea(attrs={'class': 'form-input', 'rows': 2}),
        }

    def __init__(self, *args, tenant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if tenant:
            self.fields['subject'].queryset = Subject.objects.filter(tenant=tenant, is_active=True)
            self.fields['class_obj'].queryset = Class.objects.filter(tenant=tenant, is_active=True)
        self.fields['subject'].required = False
        self.fields['class_obj'].required = False
        self.fields['subject'].widget.attrs.update({'class': 'form-input'})
        self.fields['class_obj'].widget.attrs.update({'class': 'form-input'})
