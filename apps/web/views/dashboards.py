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
        return render(request, 'dashboards/teacher_dashboard.html', {'user': user})

    if role == 'school_admin':
        from apps.service.models import Class
        from apps.accounts.models import User

        tenant = user.tenant
        ctx = {
            'user': user,
            'tenant': tenant,
            'stats': {
                'total_classes': Class.objects.filter(tenant=tenant, is_active=True).count(),
                'total_students': User.objects.filter(
                    tenant=tenant, role__name='student', is_active=True
                ).count(),
                'total_teachers': User.objects.filter(
                    tenant=tenant, role__name='teacher', is_active=True
                ).count(),
            },
        }
        return render(request, 'dashboards/school_admin_dashboard.html', ctx)

    if role == 'system_admin':
        return render(request, 'dashboards/system_admin_dashboard.html', {'user': user})

    return render(request, 'base/no_role.html', {'user': user})
