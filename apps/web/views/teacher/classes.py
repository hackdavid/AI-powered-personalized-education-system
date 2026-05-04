"""Teacher-facing Class roster pages.

Phase E.

- `class_list_view`   — every class the teacher teaches, with quick stats.
- `class_detail_view` — one class: header stats + roster + active quests +
                        per-class recent activity.
"""

from collections import defaultdict
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone

from apps.core.decorators import role_required
from apps.service.models import (
    Assignment,
    Enrollment,
    StudentAssignment,
    StudentProfile,
    XPLedger,
)
from apps.web.views.teacher.access import (
    _teacher_classes,
    teacher_class_or_404,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _avg_mastery_for_students(student_ids):
    """Mean of every (student × subject) mastery cell for the given students.

    Returns 0 if no mastery data exists yet.
    """
    if not student_ids:
        return 0
    profiles = StudentProfile.objects.filter(student_id__in=student_ids)
    total = 0.0
    n = 0
    for p in profiles:
        for _sid, pct in (p.mastery_per_subject or {}).items():
            if pct is None:
                continue
            total += float(pct)
            n += 1
    return int(round(total / n)) if n else 0


def _top_performer(student_ids):
    """Highest-XP active student or None.

    Used as a quick "who's leading" hint on each class card. Lightweight —
    one ORDER BY total_xp LIMIT 1 lookup.
    """
    if not student_ids:
        return None
    profile = (
        StudentProfile.objects
        .filter(student_id__in=student_ids)
        .select_related('student')
        .order_by('-total_xp')
        .first()
    )
    if not profile:
        return None
    return {
        'student_id': profile.student_id,
        'name': profile.student.get_full_name() or profile.student.email,
        'level': profile.level,
        'rank': profile.rank,
        'total_xp': profile.total_xp,
    }


# ---------------------------------------------------------------------------
# views
# ---------------------------------------------------------------------------


@login_required
@role_required(['teacher', 'school_admin'])
def class_list_view(request):
    """Grid of every class the teacher is involved with."""
    classes = list(_teacher_classes(request.user))
    class_ids = [c.id for c in classes]

    # One DB hit each for the per-class counts we display on cards.
    now = timezone.now()
    student_counts = dict(
        Enrollment.objects
        .filter(class_obj_id__in=class_ids, is_active=True)
        .values_list('class_obj_id')
        .annotate(n=Count('id'))
        .values_list('class_obj_id', 'n')
    )
    quest_counts = dict(
        Assignment.objects
        .filter(
            class_obj_id__in=class_ids,
            status=Assignment.STATUS_PUBLISHED,
            due_date__gte=now,
        )
        .values_list('class_obj_id')
        .annotate(n=Count('id'))
        .values_list('class_obj_id', 'n')
    )

    # Roster of student ids per class — needed for mastery + top-performer.
    enrollments = Enrollment.objects.filter(
        class_obj_id__in=class_ids,
        is_active=True,
    ).values('class_obj_id', 'student_id')
    students_by_class = defaultdict(list)
    for row in enrollments:
        students_by_class[row['class_obj_id']].append(row['student_id'])

    cards = []
    for c in classes:
        sids = students_by_class.get(c.id, [])
        cards.append({
            'id': c.id,
            'name': c.name,
            'grade_level': c.grade_level,
            'section': c.section,
            'academic_year': c.academic_year,
            'is_homeroom': c.class_teacher_id == request.user.id,
            'student_count': student_counts.get(c.id, 0),
            'active_quest_count': quest_counts.get(c.id, 0),
            'avg_mastery_pct': _avg_mastery_for_students(sids),
            'top_performer': _top_performer(sids),
        })

    return render(request, 'teacher/classes/list.html', {
        'user': request.user,
        'classes': cards,
        'active_page': 'classes',
    })


@login_required
@role_required(['teacher', 'school_admin'])
def class_detail_view(request, pk):
    """Header stats + sortable roster + active quests + recent activity."""
    cls = teacher_class_or_404(request.user, pk)

    # Roster — JOIN Enrollment with StudentProfile so we get level/rank/streak
    # in one query rather than O(n) lookups.
    enrollments = list(
        Enrollment.objects
        .filter(class_obj=cls, is_active=True)
        .select_related('student', 'student__profile')
        .order_by('student__last_name', 'student__first_name')
    )
    student_ids = [e.student_id for e in enrollments]

    sort = (request.GET.get('sort') or 'name').lower()

    roster = []
    for e in enrollments:
        s = e.student
        p = getattr(s, 'profile', None)
        roster.append({
            'student_id': s.id,
            'name': s.get_full_name() or s.email,
            'email': s.email,
            'level': getattr(p, 'level', 0) if p else 0,
            'rank': getattr(p, 'rank', 'E') if p else 'E',
            'total_xp': getattr(p, 'total_xp', 0) if p else 0,
            'streak_days': getattr(p, 'streak_days', 0) if p else 0,
            'last_active': getattr(p, 'last_active_date', None) if p else None,
            'avg_mastery': _avg_mastery_for_students([s.id]) if p else 0,
            'onboarding_complete': getattr(p, 'onboarding_complete', False) if p else False,
        })

    sort_keys = {
        'name': lambda r: (r['name'] or '').lower(),
        'level': lambda r: -r['level'],
        'rank': lambda r: '_EDCBAS'.index(r['rank']) if r['rank'] in 'EDCBAS' else 0,
        'xp': lambda r: -r['total_xp'],
        'streak': lambda r: -r['streak_days'],
        'mastery': lambda r: -r['avg_mastery'],
        'last_active': lambda r: -(r['last_active'].toordinal() if r['last_active'] else 0),
    }
    roster.sort(key=sort_keys.get(sort, sort_keys['name']))

    # Active quests for this class (published, future due)
    now = timezone.now()
    active_quests = list(
        Assignment.objects
        .filter(class_obj=cls, status=Assignment.STATUS_PUBLISHED, due_date__gte=now)
        .select_related('subject')
        .order_by('due_date')
    )

    # Submission heat: per-quest count of submitted/graded
    quest_ids = [q.id for q in active_quests]
    submitted_counts = {}
    if quest_ids:
        submitted_counts = dict(
            StudentAssignment.objects
            .filter(
                assignment_id__in=quest_ids,
                status__in=[
                    StudentAssignment.STATUS_SUBMITTED,
                    StudentAssignment.STATUS_GRADED,
                ],
            )
            .values_list('assignment_id')
            .annotate(n=Count('id'))
            .values_list('assignment_id', 'n')
        )

    quests_decorated = [{
        'id': q.id,
        'title': q.title,
        'subject_name': q.subject.name if q.subject_id else None,
        'due_date': q.due_date,
        'reward_xp': q.reward_xp,
        'submitted_count': submitted_counts.get(q.id, 0),
        'roster_size': len(student_ids),
    } for q in active_quests]

    # Recent activity scoped to this class's students only.
    recent_activity = []
    if student_ids:
        rows = (
            XPLedger.objects
            .filter(student_id__in=student_ids)
            .select_related('student')
            .order_by('-created_at')[:10]
        )
        icon_for = {
            XPLedger.SOURCE_QUEST: ('quest', 'completed a quest'),
            XPLedger.SOURCE_HUNT_TASK: ('hunt', 'cleared a hunt task'),
            XPLedger.SOURCE_HUNT_COMPLETE: ('hunt', 'finished a hunt'),
            XPLedger.SOURCE_DAILY_QUEST: ('daily', 'finished a daily quest'),
            XPLedger.SOURCE_STREAK_MILESTONE: ('streak', 'hit a streak milestone'),
            XPLedger.SOURCE_AWAKENING: ('onboard', 'completed onboarding'),
            XPLedger.SOURCE_CHAT_ACTIVITY: ('chat', 'asked the System Advisor'),
            XPLedger.SOURCE_ADMIN_ADJUSTMENT: ('admin', 'received an XP adjustment'),
        }
        for r in rows:
            icon, verb = icon_for.get(r.source, ('event', 'event'))
            recent_activity.append({
                'icon': icon,
                'student_id': r.student_id,
                'student_name': r.student.get_full_name() or r.student.email,
                'verb': verb,
                'amount': r.amount,
                'created_at': r.created_at,
            })

    # Header stats
    week_ago = timezone.now() - timedelta(days=7)
    stats = {
        'student_count': len(roster),
        'avg_mastery_pct': _avg_mastery_for_students(student_ids),
        'active_quests': len(active_quests),
        'submissions_this_week': (
            StudentAssignment.objects
            .filter(
                assignment__class_obj=cls,
                submitted_at__gte=week_ago,
            )
            .count()
        ),
    }

    return render(request, 'teacher/classes/detail.html', {
        'user': request.user,
        'class_obj': cls,
        'is_homeroom': cls.class_teacher_id == request.user.id,
        'stats': stats,
        'roster': roster,
        'sort': sort,
        'active_quests': quests_decorated,
        'recent_activity': recent_activity,
        'active_page': 'classes',
    })
