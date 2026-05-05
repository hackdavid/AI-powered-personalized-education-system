"""Teacher-facing student pages.

Phase E.

- `student_list_view`   — global roster across every class the teacher
                          teaches; filterable by class.
- `student_detail_view` — read-only progression view of one student.
                          Mirrors the student's own profile page so a
                          teacher sees exactly what the student sees,
                          plus a teacher-only header banner.
"""

from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, ExpressionWrapper, F, FloatField, Q
from django.shortcuts import render
from django.utils import timezone

from apps.accounts.models import User
from apps.core.decorators import role_required
from apps.service.models import (
    Badge,
    Class,
    EarnedBadge,
    Enrollment,
    Goal,
    OnboardingResult,
    StudentAssignment,
    StudentProfile,
    Subject,
    XPLedger,
)
from apps.web.views.teacher.access import (
    _teacher_classes,
    teacher_student_or_404,
)


@login_required
@role_required(['teacher', 'school_admin'])
def student_list_view(request):
    """Roster of every active student across the teacher's classes."""
    classes = list(_teacher_classes(request.user))
    class_ids = [c.id for c in classes]

    # Optional filter: ?class=<id> narrows the roster to that one class
    # (only if the teacher actually teaches that class).
    selected_class_id = request.GET.get('class') or ''
    try:
        selected_class_id_int = int(selected_class_id) if selected_class_id else None
    except ValueError:
        selected_class_id_int = None
    if selected_class_id_int and selected_class_id_int not in class_ids:
        selected_class_id_int = None  # silently ignore — don't leak existence

    enrollment_qs = Enrollment.objects.filter(
        class_obj_id__in=class_ids,
        is_active=True,
    ).select_related(
        'student', 'student__profile', 'class_obj',
    )
    if selected_class_id_int:
        enrollment_qs = enrollment_qs.filter(class_obj_id=selected_class_id_int)

    # One student can be enrolled in several of the teacher's classes (e.g.
    # homeroom + subject section). Collapse to one row per student and remember
    # the class names they're in.
    students_by_id = {}
    classes_by_student = defaultdict(list)
    for e in enrollment_qs.order_by('student__last_name', 'student__first_name'):
        s = e.student
        if s.id not in students_by_id:
            p = getattr(s, 'profile', None)
            students_by_id[s.id] = {
                'student_id': s.id,
                'name': s.get_full_name() or s.email,
                'email': s.email,
                'level': getattr(p, 'level', 0) if p else 0,
                'rank': getattr(p, 'rank', 'E') if p else 'E',
                'total_xp': getattr(p, 'total_xp', 0) if p else 0,
                'streak_days': getattr(p, 'streak_days', 0) if p else 0,
                'last_active': getattr(p, 'last_active_date', None) if p else None,
                'onboarding_complete': getattr(p, 'onboarding_complete', False) if p else False,
            }
        classes_by_student[s.id].append(e.class_obj.name)

    rows = []
    for sid, data in students_by_id.items():
        data['class_names'] = classes_by_student[sid]
        rows.append(data)

    sort = (request.GET.get('sort') or 'name').lower()
    sort_keys = {
        'name': lambda r: (r['name'] or '').lower(),
        'level': lambda r: -r['level'],
        'rank': lambda r: '_EDCBAS'.index(r['rank']) if r['rank'] in 'EDCBAS' else 0,
        'xp': lambda r: -r['total_xp'],
        'streak': lambda r: -r['streak_days'],
        'last_active': lambda r: -(r['last_active'].toordinal() if r['last_active'] else 0),
    }
    rows.sort(key=sort_keys.get(sort, sort_keys['name']))

    return render(request, 'teacher/students/list.html', {
        'user': request.user,
        'classes': classes,
        'selected_class_id': selected_class_id_int,
        'rows': rows,
        'sort': sort,
        'active_page': 'students',
    })


@login_required
@role_required(['teacher', 'school_admin'])
def student_detail_view(request, pk):
    """Read-only mirror of the student's profile page, plus a teacher banner.

    Access is gated by `teacher_student_or_404`: the student must be enrolled
    in at least one of the teacher's classes (homeroom or subject).
    """
    student = teacher_student_or_404(request.user, pk)
    profile, _ = StudentProfile.objects.get_or_create(student=student)
    onboarding = OnboardingResult.objects.filter(student=student).first()

    # XP history — last 15 events
    xp_events = list(
        XPLedger.objects
        .filter(student=student)
        .order_by('-created_at')[:15]
    )

    # Mastery rows
    mastery_rows = []
    if profile.mastery_per_subject:
        subject_map = {
            str(s.id): s.name
            for s in Subject.objects.filter(tenant=student.tenant)
        }
        for sid, pct in profile.mastery_per_subject.items():
            mastery_rows.append({
                'subject_name': subject_map.get(str(sid), f'Subject {sid}'),
                'pct': int(pct or 0),
            })
        mastery_rows.sort(key=lambda r: -r['pct'])

    # Quest performance
    graded_qs = StudentAssignment.objects.filter(
        student=student, status=StudentAssignment.STATUS_GRADED,
    )
    quests_graded = graded_qs.count()
    avg_pct = graded_qs.filter(max_score__gt=0).aggregate(
        avg=Avg(
            ExpressionWrapper(
                F('score') * 100.0 / F('max_score'),
                output_field=FloatField(),
            )
        )
    )['avg']
    avg_quest_pct = int(round(avg_pct)) if avg_pct is not None else None

    # Last 10 quests submitted/graded — gives the teacher a feel for trends.
    recent_quests = list(
        StudentAssignment.objects
        .filter(student=student)
        .filter(Q(status=StudentAssignment.STATUS_GRADED)
                | Q(status=StudentAssignment.STATUS_SUBMITTED))
        .select_related('assignment', 'assignment__subject')
        .order_by('-updated_at')[:10]
    )

    # Hunts: counts + active list (most useful trend for the teacher)
    hunts_completed = Goal.objects.filter(
        student=student, status=Goal.STATUS_COMPLETED,
    ).count()
    hunts_expired = Goal.objects.filter(
        student=student, status=Goal.STATUS_EXPIRED,
    ).count()
    hunts_active_qs = Goal.objects.filter(
        student=student, status=Goal.STATUS_ACTIVE,
    ).select_related('subject').order_by('-created_at')[:5]
    hunts_active_list = list(hunts_active_qs)
    hunts_active = Goal.objects.filter(
        student=student, status=Goal.STATUS_ACTIVE,
    ).count()

    # Badges
    earned_map = {
        eb.badge_id: eb
        for eb in EarnedBadge.objects.filter(student=student).select_related('badge')
    }
    all_badges = list(Badge.objects.filter(is_active=True).order_by('display_order', 'name'))
    badge_rows = []
    for b in all_badges:
        eb = earned_map.get(b.id)
        badge_rows.append({
            'badge': b,
            'earned': eb is not None,
            'earned_at': eb.created_at if eb else None,
        })

    # Which of MY classes is this student in? — useful in the header banner.
    student_classes = list(
        Class.objects
        .filter(
            tenant=request.user.tenant,
            is_active=True,
            enrollments__student=student,
            enrollments__is_active=True,
        )
        .filter(
            Q(class_teacher=request.user)
            | Q(class_subjects__teacher=request.user)
        )
        .distinct()
    )

    return render(request, 'teacher/students/detail.html', {
        'user': request.user,
        'student': student,
        'profile': profile,
        'onboarding': onboarding,
        'xp_events': xp_events,
        'mastery_rows': mastery_rows,
        'recent_quests': recent_quests,
        'quests_graded': quests_graded,
        'avg_quest_pct': avg_quest_pct,
        'hunts_completed': hunts_completed,
        'hunts_expired': hunts_expired,
        'hunts_active': hunts_active,
        'hunts_active_list': hunts_active_list,
        'badge_rows': badge_rows,
        'earned_count': len(earned_map),
        'total_badges': len(all_badges),
        'student_classes': student_classes,
        'active_page': 'students',
    })
