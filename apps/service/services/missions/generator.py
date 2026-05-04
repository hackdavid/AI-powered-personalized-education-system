"""Rule-based Mission Brief generator."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import List

from django.db import transaction
from django.utils import timezone

from apps.service.models import (
    DailyQuest,
    Goal,
    MissionBrief,
    MissionItem,
    StudentAssignment,
    StudentProfile,
    Subject,
    Task,
)

logger = logging.getLogger(__name__)


# Static daily missions (low-priority baseline — included as fallback if we
# don't have enough real work from assignments / hunts / daily quests).
STATIC_MISSIONS = [
    {
        'title': 'Visit the System Advisor',
        'description': 'Ask one question grounded in your curriculum — answers cite their sources.',
        'kind': MissionItem.KIND_CHAT,
        'xp_reward': 10,
        'priority': 20,
        'action_url': '/student/chat/',
    },
    {
        'title': 'Explore your Codex',
        'description': 'Open any cited topic from your chat or browse the curriculum directly.',
        'kind': MissionItem.KIND_PRACTICE,
        'xp_reward': 15,
        'priority': 25,
        'action_url': '/student/chat/',
    },
]


# ----------------------------------------------------------------- helpers


def _natural_due_in(due: 'datetime') -> str:
    """Return a compact 'Due in Xh'/'Due in Xd' string."""
    now = timezone.now()
    delta = due - now
    hours = int(delta.total_seconds() // 3600)
    if hours < 0:
        return 'Overdue'
    if hours < 24:
        return f'Due in {hours}h'
    days = hours // 24
    return f'Due in {days}d'


def _weakest_subject_item(student) -> dict | None:
    """Return a practice item for the student's weakest probed subject, or
    None if no mastery data exists yet."""
    try:
        profile = student.profile
    except Exception:
        return None

    mastery = profile.mastery_per_subject or {}
    if not mastery:
        return None

    # Find the subject with the lowest mastery score
    try:
        weakest_sid_str, weakest_score = min(
            mastery.items(), key=lambda kv: kv[1],
        )
        weakest_sid = int(weakest_sid_str)
    except (ValueError, TypeError):
        return None

    subject = Subject.objects.filter(pk=weakest_sid).first()
    if not subject:
        return None

    return {
        'title': f'Practice your weakest subject: {subject.name}',
        'description': (
            f'Your current mastery is {weakest_score}%. '
            f'Ask the System Advisor a {subject.name} question to close the gap.'
        ),
        'kind': MissionItem.KIND_PRACTICE,
        'xp_reward': 50,
        # Higher priority than static missions (weakness is the real signal)
        'priority': 40 + max(0, 100 - int(weakest_score)),
        'action_url': '/student/chat/',
        'related_object_type': 'subject',
        'related_object_id': weakest_sid,
    }


def _streak_item(student) -> dict | None:
    """Remind active-streak students to keep the streak alive."""
    try:
        profile = student.profile
    except Exception:
        return None

    if profile.streak_days <= 0:
        return None

    return {
        'title': f'Keep your {profile.streak_days}-day streak alive',
        'description': 'Complete any mission today to maintain your streak.',
        'kind': MissionItem.KIND_STREAK,
        'xp_reward': 5,
        'priority': 10,
        'action_url': '/dashboard/',
    }


def _assignment_items(student) -> list[dict]:
    """Surface active (pending / in_progress) assignments for this student.

    Priority ladder:
      * due in < 24h  → urgent_quest, priority 999
      * due in < 72h  → quest, priority 100
      * else          → quest, priority 60
    """
    now = timezone.now()
    sas = StudentAssignment.objects.filter(
        student=student,
        status__in=[
            StudentAssignment.STATUS_PENDING,
            StudentAssignment.STATUS_IN_PROGRESS,
        ],
    ).select_related('assignment')

    out = []
    for sa in sas:
        a = sa.assignment
        if not a:
            continue
        delta = a.due_date - now
        hours = delta.total_seconds() / 3600
        if hours < 24:
            priority = 999
            kind = MissionItem.KIND_URGENT
        elif hours < 72:
            priority = 100
            kind = MissionItem.KIND_QUEST
        else:
            priority = 60
            kind = MissionItem.KIND_QUEST

        xp_hint = (a.reward_xp or 0) // 2
        out.append({
            'title': f'Quest: {a.title}',
            'description': _natural_due_in(a.due_date),
            'kind': kind,
            'xp_reward': xp_hint,
            'priority': priority,
            'action_url': f'/student/quests/{a.id}/',
            'related_object_type': 'assignment',
            'related_object_id': a.id,
        })
    return out


def _hunt_task_items(student) -> list[dict]:
    """One mission item per active Goal — the next incomplete Task."""
    goals = Goal.objects.filter(
        student=student, status=Goal.STATUS_ACTIVE,
    ).prefetch_related('tasks')

    out = []
    for goal in goals:
        next_task = goal.tasks.filter(is_completed=False).order_by('order', 'id').first()
        if not next_task:
            continue
        out.append({
            'title': f'Hunt: {next_task.title}',
            'description': f'Part of "{goal.title}"',
            'kind': MissionItem.KIND_HUNT_TASK,
            'xp_reward': next_task.xp_reward,
            'priority': 70,
            'action_url': f'/student/hunts/{goal.id}/',
            'related_object_type': 'hunt_task',
            'related_object_id': next_task.id,
        })
    return out


_DAILY_QUEST_KIND_MAP = {
    DailyQuest.KIND_VISIT_CHAT: MissionItem.KIND_CHAT,
    DailyQuest.KIND_PRACTICE_WEAKEST: MissionItem.KIND_PRACTICE,
    DailyQuest.KIND_HUNT_TASK: MissionItem.KIND_HUNT_TASK,
    DailyQuest.KIND_STREAK: MissionItem.KIND_STREAK,
}


def _daily_quest_items(student) -> list[dict]:
    """Surface incomplete daily quests for today."""
    try:
        from apps.service.services.daily_quests import ensure_todays_daily_quests
        ensure_todays_daily_quests(student)
    except Exception as exc:
        logger.warning('ensure_todays_daily_quests failed: %s', exc)

    today = timezone.localdate()
    dqs = DailyQuest.objects.filter(
        student=student, date=today, is_completed=False,
    )

    out = []
    for dq in dqs:
        out.append({
            'title': dq.title,
            'description': dq.description,
            'kind': _DAILY_QUEST_KIND_MAP.get(dq.kind, MissionItem.KIND_PRACTICE),
            'xp_reward': dq.xp_reward,
            'priority': 15,
            'action_url': dq.action_url,
            'related_object_type': 'daily_quest',
            'related_object_id': dq.id,
        })
    return out


# ----------------------------------------------------------------- main


@transaction.atomic
def generate_mission_brief(brief: MissionBrief) -> List[MissionItem]:
    """Populate a brief with today's items. Clears any existing items first
    so the operation is idempotent."""

    # Safety: wipe any pre-existing items for a clean regeneration
    brief.items.all().delete()

    student = brief.student

    # Collect candidates (dict specs). Priority-ordered roughly:
    #   999 urgent_quest → 100/60 quest → 70 hunt_task → 40+ weakest → 20-25 static
    #   → 15 daily_quest → 10 streak.
    candidates: List[dict] = []

    # 1. Active assignments (urgent or otherwise)
    candidates.extend(_assignment_items(student))

    # 2. Hunt tasks (one per active hunt)
    candidates.extend(_hunt_task_items(student))

    # 3. Daily quests (today, incomplete) — makes sure DQ rows exist too
    candidates.extend(_daily_quest_items(student))

    # 4. Weakest subject
    weakest = _weakest_subject_item(student)
    if weakest:
        candidates.append(weakest)

    # 5. Streak reminder
    streak = _streak_item(student)
    if streak:
        candidates.append(streak)

    # Static fallback: only pull them in if we don't have enough real work yet.
    if len(candidates) < 3:
        candidates.extend(STATIC_MISSIONS)

    # Sort by descending priority
    candidates.sort(key=lambda c: -c.get('priority', 0))

    # Cap at 5 items
    items: List[MissionItem] = []
    for spec in candidates[:5]:
        item = MissionItem.objects.create(
            brief=brief,
            title=spec['title'],
            description=spec.get('description', ''),
            kind=spec['kind'],
            xp_reward=spec['xp_reward'],
            priority=spec['priority'],
            action_url=spec.get('action_url', ''),
            related_object_type=spec.get('related_object_type', ''),
            related_object_id=spec.get('related_object_id') or None,
        )
        items.append(item)

    return items


def ensure_todays_brief(student) -> MissionBrief:
    """Return today's brief, creating + populating it if it doesn't exist.

    Side effect: expires old uncompleted items on any prior briefs.
    """
    today = timezone.localdate()

    # Expire yesterday-and-earlier uncompleted items so the dashboard can
    # safely treat non-expired non-completed items as "still active".
    expire_old_briefs(student, up_to_date=today)

    brief, created = MissionBrief.objects.get_or_create(
        student=student, date=today,
    )
    if created or not brief.items.exists():
        generate_mission_brief(brief)
    return brief


def expire_old_briefs(student, up_to_date: date) -> int:
    """Mark uncompleted items on briefs older than `up_to_date` as expired.
    Returns count of items expired."""
    qs = MissionItem.objects.filter(
        brief__student=student,
        brief__date__lt=up_to_date,
    ).exclude(status__in=[MissionItem.STATUS_COMPLETED, MissionItem.STATUS_EXPIRED])
    count = qs.count()
    if count:
        qs.update(status=MissionItem.STATUS_EXPIRED, updated_at=timezone.now())
    return count


def mark_item_completed_for_event(
    student, related_type: str, related_id: int,
) -> bool:
    """Find today's MissionItem for this (type, id) and mark it completed.

    Used after grading an assignment or completing a hunt task so the
    student's dashboard briefs stay in sync with the underlying work.

    Returns True if an item was updated, False otherwise.
    """
    if not related_type or related_id is None:
        return False
    today = timezone.localdate()
    item = MissionItem.objects.filter(
        brief__student=student,
        brief__date=today,
        related_object_type=related_type,
        related_object_id=related_id,
    ).exclude(status=MissionItem.STATUS_COMPLETED).first()
    if not item:
        return False
    item.mark_completed()
    return True
