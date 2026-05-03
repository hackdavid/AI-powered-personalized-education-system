"""DailyQuest generator - system-picks 3-5 daily challenges based on rules.

Idempotent per (student, date, kind). Called on each dashboard load.
"""

import logging
from typing import List, Optional

from django.utils import timezone

from apps.service.models import DailyQuest, Goal, Subject

logger = logging.getLogger(__name__)


def _has_active_hunt(student) -> bool:
    return Goal.objects.filter(
        student=student, status=Goal.STATUS_ACTIVE,
    ).exclude(tasks__isnull=True).exists()


def _weakest_subject_name(student) -> Optional[str]:
    try:
        mastery = student.profile.mastery_per_subject or {}
    except Exception:
        return None
    if not mastery:
        return None
    try:
        sid = min(mastery, key=lambda k: mastery[k])
        s = Subject.objects.filter(pk=int(sid)).first()
        return s.name if s else None
    except (ValueError, TypeError):
        return None


def ensure_todays_daily_quests(student) -> List[DailyQuest]:
    today = timezone.localdate()
    quests: List[DailyQuest] = []

    # Always include the chat visit
    q, _ = DailyQuest.objects.get_or_create(
        student=student, date=today, kind=DailyQuest.KIND_VISIT_CHAT,
        defaults={
            'title': 'Ask the System Advisor',
            'description': 'Open the advisor and ask one curriculum question.',
            'xp_reward': 10,
            'action_url': '/student/chat/',
        },
    )
    quests.append(q)

    # Weakest-subject practice if mastery data exists
    weak = _weakest_subject_name(student)
    if weak:
        q, _ = DailyQuest.objects.get_or_create(
            student=student, date=today, kind=DailyQuest.KIND_PRACTICE_WEAKEST,
            defaults={
                'title': f'Practice {weak}',
                'description': f'Work on your weakest subject: {weak}.',
                'xp_reward': 50,
                'action_url': '/student/chat/',
            },
        )
        quests.append(q)

    # Hunt-task quest if there's at least one active hunt with tasks
    if _has_active_hunt(student):
        q, _ = DailyQuest.objects.get_or_create(
            student=student, date=today, kind=DailyQuest.KIND_HUNT_TASK,
            defaults={
                'title': 'Advance a Hunt',
                'description': 'Complete one task on any active Hunt.',
                'xp_reward': 30,
                'action_url': '/student/hunts/',
            },
        )
        quests.append(q)

    # Streak quest if the student has a live streak
    try:
        if student.profile.streak_days > 0:
            q, _ = DailyQuest.objects.get_or_create(
                student=student, date=today, kind=DailyQuest.KIND_STREAK,
                defaults={
                    'title': f'Keep your {student.profile.streak_days}-day streak',
                    'description': 'Complete any mission today to keep your streak alive.',
                    'xp_reward': 5,
                    'action_url': '/dashboard/',
                },
            )
            quests.append(q)
    except Exception:
        pass

    return quests
