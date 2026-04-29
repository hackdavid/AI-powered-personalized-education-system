"""
URL configuration for apps.web.

Organized into three namespaces, all included in config/urls.py:
- auth:           login / logout / password
- school_admin:   school admin CRUD UIs
- web:            home + dashboard
"""

from django.urls import path

from apps.web.views import public, dashboards, auth as auth_views
from apps.web.views.school_admin import (
    class_views,
    subject_views,
    teacher_views,
    student_views,
    document_views,
)


# --- public + dashboard (namespace 'web') ---
public_patterns = [
    path('', public.home, name='home'),
    path('dashboard/', dashboards.dashboard_router, name='dashboard'),
]


# --- auth (namespace 'auth') ---
auth_patterns = [
    path('login/', auth_views.login_view, name='login'),
    path('logout/', auth_views.logout_view, name='logout'),
    path('password-change/', auth_views.password_change_view, name='password_change'),
    path('password-reset/', auth_views.password_reset_request_view, name='password_reset'),
]


# --- school admin (namespace 'school_admin') ---
school_admin_patterns = [
    # Classes
    path('classes/', class_views.class_list, name='class_list'),
    path('classes/create/', class_views.class_create, name='class_create'),
    path('classes/<int:pk>/', class_views.class_detail, name='class_detail'),
    path('classes/<int:pk>/edit/', class_views.class_edit, name='class_edit'),
    path('classes/<int:pk>/delete/', class_views.class_delete, name='class_delete'),
    path('classes/<int:pk>/assign-subject/', class_views.assign_subject, name='assign_subject'),
    path('classes/<int:pk>/assignments/<int:csid>/update/', class_views.assignment_update, name='assignment_update'),
    path('classes/<int:pk>/remove-subject/<int:csid>/', class_views.remove_subject, name='remove_subject'),

    # Subjects
    path('subjects/', subject_views.subject_list, name='subject_list'),
    path('subjects/create/', subject_views.subject_create, name='subject_create'),
    path('subjects/<int:pk>/edit/', subject_views.subject_edit, name='subject_edit'),
    path('subjects/<int:pk>/delete/', subject_views.subject_delete, name='subject_delete'),

    # Teachers
    path('teachers/', teacher_views.teacher_list, name='teacher_list'),
    path('teachers/invite/', teacher_views.teacher_invite, name='teacher_invite'),
    path('teachers/<int:pk>/edit/', teacher_views.teacher_edit, name='teacher_edit'),
    path('teachers/<int:pk>/toggle-active/', teacher_views.teacher_toggle_active, name='teacher_toggle_active'),

    # Students
    path('students/', student_views.student_list, name='student_list'),
    path('students/invite/', student_views.student_invite, name='student_invite'),
    path('students/<int:pk>/edit/', student_views.student_edit, name='student_edit'),
    path('students/<int:pk>/toggle-active/', student_views.student_toggle_active, name='student_toggle_active'),

    # Documents
    path('documents/', document_views.document_list, name='document_list'),
    path('documents/upload/', document_views.document_upload, name='document_upload'),
    path('documents/<int:pk>/delete/', document_views.document_delete, name='document_delete'),
]
