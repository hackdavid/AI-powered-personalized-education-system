"""Hunt (Goal) → Task decomposition, LLM-primary with stub fallback.

Input: a Goal the student just created.
Output: list of Task rows persisted under that Goal. Sets goal.decomposed_at
so the UI knows the plan is ready.
"""

import json
import logging
import re
from typing import List

from django.conf import settings
from django.utils import timezone

from apps.service.models import ContentNode, Task

logger = logging.getLogger(__name__)


STUB_TEMPLATE = [
    ('Read the relevant topic', 'read', 15,
     'Open the Codex to the topic your Hunt centres on.'),
    ('Ask the System Advisor 5 questions', 'chat', 25,
     'Deepen your understanding by chatting with your curriculum-grounded tutor.'),
    ('Practice 5 MCQ problems', 'practice', 30,
     'Lock it in with hands-on practice.'),
    ('Self-quiz (5 Q)', 'quiz', 40,
     'Quick check — are the core ideas stable?'),
    ('Reflect — 3 takeaways', 'reflect', 20,
     'Write three things you now know that you did not before.'),
    ('BOSS: 10-Q final', 'boss', 70,
     'Prove you mastered the topic. \u2265 70% to clear the Hunt.'),
]


def _stub_decomposition(goal) -> List[dict]:
    return [
        {'title': t, 'kind': k, 'xp_reward': xp, 'description': d,
         'order': i, 'ref_node_id': None}
        for i, (t, k, xp, d) in enumerate(STUB_TEMPLATE)
    ]


def _candidate_nodes_for_goal(goal, limit: int = 8):
    qs = ContentNode.objects.filter(tenant=goal.student.tenant)
    if goal.subject:
        qs = qs.filter(subject=goal.subject)
    qs = qs.filter(node_type__in=['topic', 'section']).order_by('?')[:limit]
    return list(qs)


def _service_is_configured(service) -> bool:
    """Handle both property and callable forms of is_configured."""
    is_conf = getattr(service, 'is_configured', None)
    if callable(is_conf):
        try:
            is_conf = is_conf()
        except Exception:
            is_conf = None
    if is_conf is None:
        return bool(getattr(settings, 'OPENAI_API_KEY', None))
    return bool(is_conf)


def _llm_decomposition(goal) -> List[dict]:
    """Ask the LLM to split the Goal into tasks. Returns list of task dicts."""
    try:
        from clients.llm import LLMService
    except Exception:
        logger.info('LLMService import failed; falling back to stub')
        return _stub_decomposition(goal)

    service = LLMService()
    if not _service_is_configured(service):
        logger.info('LLM not configured (no OPENAI_API_KEY); using stub')
        return _stub_decomposition(goal)

    try:
        mastery = {}
        if hasattr(goal.student, 'profile'):
            mastery = goal.student.profile.mastery_per_subject or {}

        candidates = _candidate_nodes_for_goal(goal)
        node_summaries = [
            {'id': n.id, 'node_id': n.node_id, 'title': n.title, 'type': n.node_type}
            for n in candidates
        ]

        system = (
            'You are an educational coach. Decompose a student goal into '
            '5-8 ordered tasks suitable for a 1-3 week Hunt. Mix kinds: '
            'read, chat, practice, quiz, reflect, boss (boss = final check). '
            'Return ONLY a JSON array; no commentary.'
        )
        prompt = (
            f'Goal title: {goal.title}\n'
            f'Description: {goal.description or "(none)"}\n'
            f'Student grade: {getattr(goal.student, "grade_level", "unknown")}\n'
            f'Target date: {goal.target_date.isoformat()}\n'
            f'Mastery by subject_id: {json.dumps(mastery)}\n'
            f'Candidate curriculum nodes: {json.dumps(node_summaries)}\n\n'
            'Each JSON item: {"title": str, "description": str, '
            '"kind": "read"|"chat"|"practice"|"quiz"|"reflect"|"boss", '
            '"xp_reward": int (15-80), "order": 0-based int, '
            '"ref_node_id": int or null (prefer picking from candidates)}.'
        )
        raw = service.generate(prompt=prompt, system=system, temperature=0.4, max_tokens=1500)
        cleaned = re.sub(r'^```json\s*|```\s*$', '', raw.strip())
        cleaned = re.sub(r'^```|```$', '', cleaned.strip())
        data = json.loads(cleaned)
        if not isinstance(data, list) or not data:
            raise ValueError('LLM did not return a non-empty list')
        return [
            {
                'title': str(item.get('title', 'Task'))[:200],
                'description': str(item.get('description', ''))[:1000],
                'kind': item.get('kind', 'practice'),
                'xp_reward': max(5, min(int(item.get('xp_reward', 25)), 120)),
                'order': int(item.get('order', i)),
                'ref_node_id': item.get('ref_node_id') if isinstance(item.get('ref_node_id'), int) else None,
            }
            for i, item in enumerate(data)
        ]
    except Exception as exc:
        logger.warning('LLM decomposition failed: %s - falling back to stub', exc)
        return _stub_decomposition(goal)


def decompose_goal(goal, *, force: bool = False) -> List[Task]:
    """Create Task rows for the Goal.

    Idempotent unless `force=True`: if tasks already exist, just return them.
    Rate-limit: once per 24h per goal if force=True (raises ValueError if called again sooner).
    """
    existing = list(goal.tasks.all())
    if existing and not force:
        return existing

    if force and goal.decomposed_at:
        elapsed = timezone.now() - goal.decomposed_at
        if elapsed.total_seconds() < 24 * 3600:
            raise ValueError('Decomposition already ran in the last 24 hours')

    specs = _llm_decomposition(goal)
    if existing:
        goal.tasks.all().delete()

    valid_kinds = {k for k, _ in Task.KIND_CHOICES}

    created = []
    for spec in specs:
        kind = spec['kind'] if spec.get('kind') in valid_kinds else Task.KIND_PRACTICE
        ref_id = spec.get('ref_node_id')
        if ref_id is not None:
            if not ContentNode.objects.filter(pk=ref_id, tenant=goal.student.tenant).exists():
                ref_id = None
        created.append(Task.objects.create(
            goal=goal,
            order=spec['order'],
            title=spec['title'],
            description=spec['description'],
            kind=kind,
            xp_reward=spec['xp_reward'],
            ref_node_id=ref_id,
        ))

    goal.decomposed_at = timezone.now()
    goal.decomposition_error = ''
    goal.save(update_fields=['decomposed_at', 'decomposition_error', 'updated_at'])

    return created
