"""Role-aware dashboard router.

For students, the dashboard is the "Status Window" — a data-driven overview
of Quests, Hunts, Mastery, Mission Brief and Streak. `_student_status_view`
does all the data assembly; `dashboard_router` just dispatches by role.
"""

from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import render, redirect
from django.utils import timezone


# ---------------------------------------------------------------------------
# Student dashboard — "Status Window"
# ---------------------------------------------------------------------------


def _mastery_rows(profile):
    """Return [{'subject_name', 'pct'}] rows for the Mastery panel."""
    from apps.service.models import Subject

    rows = []
    mastery = profile.mastery_per_subject or {}
    if not mastery:
        return rows

    subject_map = {
        str(s.id): s.name
        for s in Subject.objects.filter(tenant=profile.student.tenant)
    }
    for sid, pct in mastery.items():
        rows.append({
            'subject_name': subject_map.get(str(sid), f'Subject {sid}'),
            'pct': int(pct or 0),
        })
    rows.sort(key=lambda r: -r['pct'])
    return rows


def _streak_grid(profile):
    """Build a 7-day streak grid for the UI (Mon → Sun of the CURRENT week).

    Returns a list of 7 dicts, each with:
        {'date': ISO string, 'label': 'M'/'T'/..., 'is_today': bool,
         'is_active': bool (had an XP event that day)}
    """
    from apps.service.models import XPLedger

    today = timezone.localdate()
    # Monday as week start — matches the weekly shield refill logic.
    monday = today - timedelta(days=today.weekday())

    # One DB hit for the week's XP activity dates.
    active_dates = set(
        XPLedger.objects.filter(
            student=profile.student,
            created_at__date__gte=monday,
            created_at__date__lte=monday + timedelta(days=6),
        ).dates('created_at', 'day')
    )

    labels = ['M', 'T', 'W', 'T', 'F', 'S', 'S']
    grid = []
    for i in range(7):
        d = monday + timedelta(days=i)
        grid.append({
            'date': d.isoformat(),
            'label': labels[i],
            'is_today': d == today,
            'is_active': d in active_dates,
        })
    return grid


def _student_status_view(request):
    """Render the student 'Status Window' dashboard.

    Reads live data for Quests (Assignments), Hunts (Goals), Mastery,
    Streak, and the persisted Mission Brief. Also ticks the streak
    engine forward on every visit.
    """
    from apps.service.models import (
        Goal,
        MissionItem,
        StudentAssignment,
        StudentProfile,
    )
    from apps.service.services.missions import ensure_todays_brief
    from apps.service.services.streaks import recompute_streak
    from apps.web.views.student.quests import (
        _student_assignments_qs,
        build_quest_rows,
    )

    user = request.user

    profile, _ = StudentProfile.objects.get_or_create(student=user)

    # Tick the streak engine (idempotent per day).
    streak_result = recompute_streak(profile)
    profile.refresh_from_db()

    # --- Mission Brief -----------------------------------------------------
    try:
        brief = ensure_todays_brief(user)
        items = list(
            brief.items.exclude(status=MissionItem.STATUS_EXPIRED)
            .order_by('-priority', 'id')
        )
    except Exception:
        brief = None
        items = []

    # --- Mastery rows ------------------------------------------------------
    mastery_rows = _mastery_rows(profile)

    # --- Streak grid (7-day) ----------------------------------------------
    streak_days = _streak_grid(profile)

    # --- Active Quests -----------------------------------------------------
    active_statuses = [
        StudentAssignment.STATUS_PENDING,
        StudentAssignment.STATUS_IN_PROGRESS,
    ]
    active_quest_count = StudentAssignment.objects.filter(
        student=user, status__in=active_statuses,
    ).count()
    overdue_quest_count = StudentAssignment.objects.filter(
        student=user,
        status__in=active_statuses,
        assignment__due_date__lt=timezone.now(),
    ).count()

    # Top 3 active quests (rows enriched for template rendering).
    quest_rows = build_quest_rows(user, _student_assignments_qs(user))
    active_quest_rows = [
        r for r in quest_rows if r['status'] in active_statuses
    ][:3]

    # --- Active Hunts ------------------------------------------------------
    active_hunt_rows = list(
        Goal.objects.filter(student=user, status=Goal.STATUS_ACTIVE)
        .select_related('subject')
        .order_by('target_date')[:3]
    )

    ctx = {
        'user': user,
        'profile': profile,
        'streak_result': streak_result,

        # Status Window sections
        'mastery_rows': mastery_rows,
        'streak_days': streak_days,   # 7-day grid
        'brief': brief,
        'items': items,

        # Part A data (new)
        'active_quest_count': active_quest_count,
        'overdue_quest_count': overdue_quest_count,
        'active_quest_rows': active_quest_rows,
        'active_hunt_rows': active_hunt_rows,

        'active_page': 'status',
    }
    return render(request, 'student/status.html', ctx)


# ---------------------------------------------------------------------------
# Dashboard router
# ---------------------------------------------------------------------------


@login_required
def dashboard_router(request):
    """Route the authenticated user to their role-specific dashboard."""
    user = request.user

    # Django superuser -> superadmin dashboard (full technical access)
    if user.is_superuser:
        return render(request, 'dashboards/superadmin_dashboard.html', {'user': user})

    role = user.role_name

    if role == 'student':
        # Onboarding wall — if the student hasn't finished the Awakening,
        # route them there. The middleware (owned by another subagent)
        # normally handles this, but we guard here too so the dashboard
        # view never leaks data for un-onboarded students.
        from apps.service.models import StudentProfile
        profile = StudentProfile.objects.filter(student=user).first()
        if profile and not profile.onboarding_complete:
            return redirect('student:awakening')
        return _student_status_view(request)

    if role == 'teacher':
        return teacher_status_view(request)

    if role == 'school_admin':
        # Redirect to the new comprehensive school admin dashboard
        return redirect('school_admin:dashboard')

    if role == 'system_admin':
        return render(request, 'dashboards/system_admin_dashboard.html', {'user': user})

    return render(request, 'base/no_role.html', {'user': user})


# ---------------------------------------------------------------------------
# Teacher dashboard — "Mission Control"
# ---------------------------------------------------------------------------


def _teacher_recent_activity(teacher, student_ids, limit=10):
    """Last `limit` notable events from the teacher's students.

    Pulls from XPLedger (already the canonical timeline of student progression
    events) and renders an icon + headline + timestamp per row.
    """
    from apps.service.models import XPLedger

    if not student_ids:
        return []

    rows = (
        XPLedger.objects
        .filter(student_id__in=student_ids)
        .select_related('student')
        .order_by('-created_at')[:limit]
    )

    # Map XPLedger.source -> (icon-name, verb)
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

    out = []
    for r in rows:
        icon, verb = icon_for.get(r.source, ('event', 'event'))
        out.append({
            'icon': icon,
            'student_name': r.student.get_full_name() or r.student.email,
            'verb': verb,
            'amount': r.amount,
            'description': r.description,
            'created_at': r.created_at,
        })
    return out


def _teacher_status_context(user):
    """Assemble the data backing the teacher dashboard.

    Pulled out of the view function so tests can call it directly without
    setting up the full request/middleware stack.
    """
    from apps.service.models import (
        Assignment,
        Enrollment,
        StudentAssignment,
        StudentProfile,
    )
    from apps.web.views.teacher.quests import _teacher_classes

    classes = list(_teacher_classes(user))
    class_ids = [c.id for c in classes]

    # ---- Roster: every active student in any of my classes ----
    student_ids = list(
        Enrollment.objects
        .filter(class_obj_id__in=class_ids, is_active=True)
        .values_list('student_id', flat=True)
        .distinct()
    )

    # ---- Stat: Active Assignments (published, due in the future) ----
    now = timezone.now()
    active_assignments_count = (
        Assignment.objects
        .filter(
            tenant=user.tenant,
            class_obj_id__in=class_ids,
            status=Assignment.STATUS_PUBLISHED,
            due_date__gte=now,
        )
        .count()
    )

    # ---- Stat: Pending Reviews (submitted, awaiting grading) ----
    # Anything submitted but not yet graded — covers essays/uploads waiting
    # for the teacher even after auto-grading runs on MCQ-only quests.
    pending_reviews_count = (
        StudentAssignment.objects
        .filter(
            assignment__tenant=user.tenant,
            assignment__class_obj_id__in=class_ids,
            status=StudentAssignment.STATUS_SUBMITTED,
        )
        .count()
    )

    # ---- Stat: Avg class mastery % ----
    # mastery_per_subject is a JSONField on StudentProfile; aggregate in
    # Python because there's no portable SQL JSON aggregate across DB
    # backends.
    profiles = StudentProfile.objects.filter(student_id__in=student_ids)
    mastery_total = 0.0
    mastery_count = 0
    for p in profiles:
        for _sid, pct in (p.mastery_per_subject or {}).items():
            if pct is None:
                continue
            mastery_total += float(pct)
            mastery_count += 1
    avg_mastery_pct = int(round(mastery_total / mastery_count)) if mastery_count else 0

    # ---- My Classes: card per class ----
    class_cards = []
    if class_ids:
        # One DB hit each for student counts and active-quest counts.
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
        for c in classes:
            class_cards.append({
                'id': c.id,
                'name': c.name,
                'grade_level': c.grade_level,
                'section': c.section,
                'academic_year': c.academic_year,
                'is_homeroom': c.class_teacher_id == user.id,
                'student_count': student_counts.get(c.id, 0),
                'active_quest_count': quest_counts.get(c.id, 0),
            })

    # ---- Recent activity (XPLedger feed) ----
    recent_activity = _teacher_recent_activity(user, student_ids, limit=10)

    return {
        'user': user,
        'stats': {
            'total_students': len(student_ids),
            'total_classes': len(classes),
            'active_assignments': active_assignments_count,
            'pending_reviews': pending_reviews_count,
            'avg_mastery_pct': avg_mastery_pct,
        },
        'classes': class_cards,
        'recent_activity': recent_activity,
        'active_page': 'dashboard',
    }


@login_required
def teacher_status_view(request):
    """Render the teacher dashboard ("Mission Control")."""
    user = request.user
    if user.role_name != 'teacher' and not user.is_superuser:
        return redirect('web:dashboard')
    ctx = _teacher_status_context(user)
    return render(request, 'dashboards/teacher_dashboard.html', ctx)
