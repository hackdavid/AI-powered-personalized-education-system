"""Final step of the Awakening — mark profile complete and seed today's mission brief."""

from __future__ import annotations

from apps.service.models import OnboardingResult, StudentProfile
from apps.service.services.missions import ensure_todays_brief


def complete_awakening(student) -> StudentProfile:
    """Idempotent finalization: copy onboarding answers onto the profile,
    mark onboarding_complete, and ensure today's MissionBrief exists."""

    result, _ = OnboardingResult.objects.get_or_create(student=student)
    profile, _ = StudentProfile.objects.get_or_create(student=student)

    # 1. Identity → profile
    identity = result.step_1_identity or {}
    if identity.get('hunter_title'):
        profile.hunter_title = identity['hunter_title']
    if identity.get('interest_tags'):
        profile.interest_tags = list(identity['interest_tags'])

    # 2. Learning style → profile
    profile.learning_style = result.step_2_learning_style or {}

    # 3. Goal (stored in onboarding; actual Hunt creation is Phase B).

    # 4. Aptitude: mastery was applied by apply_calibration already.

    # 5. Rank: calibrated rank wins over default 'E'; never higher than 'C'.
    calibrated = (result.calibrated_rank or 'E').upper()
    if calibrated in ('C', 'D', 'E'):
        profile.rank = calibrated
    else:
        profile.rank = 'E'

    profile.onboarding_complete = True
    profile.save()

    result.mark_complete()

    # Seed today's mission brief via the real generator.
    ensure_todays_brief(student)

    # Badges: First Steps fires on awakening complete + rank badges if
    # calibration landed the student at D or C. Wrapped so any failure
    # never blocks the Awakening → redirect-to-dashboard flow.
    try:
        from apps.service.services.badges import evaluate_and_award
        evaluate_and_award(student, event_type='awakening_complete')
    except Exception:  # pragma: no cover — defensive
        pass

    return profile
