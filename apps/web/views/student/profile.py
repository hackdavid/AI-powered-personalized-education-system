"""Student-facing Hunter profile page.

Reads only — no mutations. Surfaces:
  - Hunter Status banner (same shape as the dashboard).
  - [ STATS ] panel — XP / Level / Rank / Hunter Title / Streak.
  - [ MASTERY ] panel — full subject list (not capped at 3 like dashboard).
  - [ XP HISTORY ] panel — last 15 XPLedger rows.
  - [ JOURNEY ] panel — counts: hunts completed / expired / quests graded / avg quest %.
  - [ ACHIEVEMENTS ] panel — empty state for now (Phase C).

Walled by OnboardingRequiredMiddleware like every other /student/ route.
"""

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, F, FloatField, ExpressionWrapper
from django.shortcuts import render

from apps.core.decorators import role_required
from apps.service.models import (
    Badge, EarnedBadge, Goal, OnboardingResult, StudentAssignment,
    StudentProfile, Subject,
)
from apps.service.services.xp import get_recent_xp_events


@login_required
@role_required(['student'])
def profile_view(request):
    user = request.user
    profile, _ = StudentProfile.objects.get_or_create(student=user)
    onboarding = OnboardingResult.objects.filter(student=user).first()

    xp_events = get_recent_xp_events(user, limit=15)

    # Build mastery rows with subject names (same approach as dashboard).
    mastery_rows = []
    if profile.mastery_per_subject:
        subject_map = {
            str(s.id): s.name for s in Subject.objects.filter(tenant=user.tenant)
        }
        for sid, pct in profile.mastery_per_subject.items():
            mastery_rows.append({
                'subject_id': sid,
                'subject_name': subject_map.get(str(sid), f'Subject {sid}'),
                'pct': int(pct),
            })
        mastery_rows.sort(key=lambda r: -r['pct'])  # highest first on profile

    # Journey stats — counts + average quest score.
    hunts_completed = Goal.objects.filter(
        student=user, status=Goal.STATUS_COMPLETED,
    ).count()
    hunts_expired = Goal.objects.filter(
        student=user, status=Goal.STATUS_EXPIRED,
    ).count()
    hunts_active = Goal.objects.filter(
        student=user, status=Goal.STATUS_ACTIVE,
    ).count()

    graded_qs = StudentAssignment.objects.filter(
        student=user, status=StudentAssignment.STATUS_GRADED,
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

    # Achievements — earned badges + the locked catalog.
    earned_map = {
        eb.badge_id: eb
        for eb in EarnedBadge.objects.filter(student=user).select_related('badge')
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

    return render(request, 'student/profile/detail.html', {
        'user': user,
        'profile': profile,
        'onboarding': onboarding,
        'xp_events': xp_events,
        'mastery_rows': mastery_rows,
        'hunts_completed': hunts_completed,
        'hunts_expired': hunts_expired,
        'hunts_active': hunts_active,
        'quests_graded': quests_graded,
        'avg_quest_pct': avg_quest_pct,
        'badge_rows': badge_rows,
        'earned_count': len(earned_map),
        'total_badges': len(all_badges),
        'active_page': 'profile',
    })
