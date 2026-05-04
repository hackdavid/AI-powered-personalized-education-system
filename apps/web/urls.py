"""
URL configuration for apps.web.

Organized into four namespaces, all included in config/urls.py:
- auth:           login / logout / password
- school_admin:   school admin CRUD UIs
- student:        student-only pages (chat / progress / goals)
- web:            home + dashboard
"""

from django.urls import path
from django.views.generic import TemplateView

from apps.web.views import public, dashboards, auth as auth_views
from apps.web.views.school_admin import (
    class_views,
    subject_views,
    teacher_views,
    student_views,
    document_views,
)
from apps.web.views.student import chat as student_chat_views
from apps.web.views.student import profile as profile_views
from apps.web.views.student import (
    awakening as awakening_views,
    codex as codex_views,
    hunts as hunts_views,
    quests as quests_views,
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


# --- student (namespace 'student') ---
student_patterns = [
    path('chat/', student_chat_views.chat_view, name='chat'),
    path('chat/<int:session_id>/', student_chat_views.chat_view, name='chat_session'),
    path('profile/', profile_views.profile_view, name='profile'),

    # Awakening (onboarding)
    path('awakening/', awakening_views.welcome_view, name='awakening'),
    path('awakening/identity/', awakening_views.identity_view, name='awakening_identity'),
    path('awakening/learning-style/', awakening_views.learning_style_view, name='awakening_learning_style'),
    path('awakening/goal/', awakening_views.goal_view, name='awakening_goal'),
    path('awakening/aptitude/', awakening_views.aptitude_view, name='awakening_aptitude'),
    path('awakening/complete/', awakening_views.complete_view, name='awakening_complete'),

    # Quests (Assignments)
    path('quests/', quests_views.quest_list_view, name='quest_list'),
    path('quests/<int:pk>/', quests_views.quest_chamber_view, name='quest_chamber'),
    path('quests/<int:pk>/save/', quests_views.quest_save_draft_view, name='quest_save_draft'),
    path('quests/<int:pk>/submit/', quests_views.quest_submit_view, name='quest_submit'),
    path('quests/<int:pk>/results/', quests_views.quest_results_view, name='quest_results'),

    # Hunts (Goals)
    path('hunts/', hunts_views.hunt_list_view, name='hunt_list'),
    path('hunts/new/', hunts_views.hunt_new_view, name='hunt_new'),
    path('hunts/<int:pk>/', hunts_views.hunt_detail_view, name='hunt_detail'),
    path('hunts/<int:pk>/abandon/', hunts_views.hunt_abandon_view, name='hunt_abandon'),
    path('hunts/tasks/<int:task_pk>/quiz/', hunts_views.hunt_task_quiz_view, name='hunt_task_quiz'),

    # Codex (curriculum browser)
    path('codex/', codex_views.codex_list_view, name='codex_list'),
    path('codex/subject/<int:subject_id>/', codex_views.codex_subject_view, name='codex_subject'),
    path('codex/node/<int:node_id>/', codex_views.codex_node_view, name='codex_node'),

    # Dev preview route (the Phase A tests assert it exists). Harmless in prod.
    path(
        'shell-preview/',
        TemplateView.as_view(template_name='student/_shell_preview.html'),
        name='shell_preview',
    ),
]
