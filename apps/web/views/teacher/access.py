"""Shared access-control helpers for the teacher area.

The teacher experience exposes other students' progress, grades, and (in
later phases) actions affecting them — so every view must verify that the
target object actually belongs to one of the requesting teacher's classes.
These helpers raise Http404 instead of returning empty data, so a curious
URL probe can't enumerate object IDs.

`_teacher_classes` already lives in `quests.py`; we re-export it here so
new modules don't have to import from a sibling.
"""

from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404

from apps.service.models import Class, Enrollment

# Re-export the existing helper so callers in this package have one
# canonical import path.
from apps.web.views.teacher.quests import _teacher_classes  # noqa: F401


def teacher_class_or_404(user, pk):
    """Return the `Class` if the teacher has access; raise Http404 otherwise.

    "Access" means same tenant + (homeroom teacher OR subject teacher of
    the class). All Class-scoped Phase E views funnel through here.
    """
    cls = get_object_or_404(
        Class,
        pk=pk,
        tenant=user.tenant,
        is_active=True,
    )
    has_access = (
        cls.class_teacher_id == user.id
        or cls.class_subjects.filter(teacher=user).exists()
    )
    if not has_access:
        raise Http404('Class not found.')
    return cls


def teacher_student_or_404(user, pk):
    """Return the student User if they're enrolled in any of the teacher's
    classes (and same tenant); raise Http404 otherwise.

    This is the gate for `/teacher/students/<id>/`. We do NOT just check the
    student's own tenant — the teacher must actually teach this student
    (homeroom or subject) for the view to be allowed. That keeps a teacher
    from probing the dashboard of, say, a student in another homeroom whose
    classes they don't touch.
    """
    from apps.accounts.models import User

    student = get_object_or_404(
        User,
        pk=pk,
        tenant=user.tenant,
        role__name='student',
        is_active=True,
    )
    teacher_class_ids = list(
        Class.objects
        .filter(tenant=user.tenant, is_active=True)
        .filter(Q(class_teacher=user) | Q(class_subjects__teacher=user))
        .values_list('id', flat=True)
    )
    if not Enrollment.objects.filter(
        class_obj_id__in=teacher_class_ids,
        student=student,
        is_active=True,
    ).exists():
        raise Http404('Student not found.')
    return student
