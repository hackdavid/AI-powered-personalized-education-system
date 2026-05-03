"""Adaptive aptitude probe for the Awakening flow.

Given a student, pick 1-2 ContentNodes per subject in their tenant and
generate MCQs. If no OPENAI_API_KEY is set, the underlying
QuestionGenerator may fail — we catch that and return a canned MCQ so
the flow stays testable offline.
"""

from __future__ import annotations

import logging
import random
from typing import Dict, List, Tuple

from apps.service.models import ContentNode, Subject
from apps.service.services.assessments.question_generator import QuestionGenerator

logger = logging.getLogger(__name__)


def _canned_mcq(node: ContentNode, subject: Subject) -> dict:
    """Deterministic stub when LLM is unavailable."""
    correct = node.title
    distractors = [
        f'Not related to {subject.name}',
        f'A topic from a different subject',
        f'None of the above',
    ]
    options = [correct] + distractors
    random.Random(node.id).shuffle(options)
    return {
        'question': f'Which of these is a topic in {subject.name} related to "{node.title}"?',
        'options': options,
        'correct_answer': correct,
    }


def get_aptitude_questions(student, num_questions: int = 5) -> List[Dict]:
    """Return a list of aptitude questions for the given student.

    Each item: {id, subject_id, subject_name, node_id, question, options,
    correct_answer}. `id` is a stable 0-indexed integer for ordering.
    """
    tenant = student.tenant
    if tenant is None:
        return []

    subjects = list(Subject.objects.filter(tenant=tenant, is_active=True)[:5])
    if not subjects:
        return []

    generator = QuestionGenerator()
    questions: List[Dict] = []
    rng = random.Random(student.pk)

    # Round-robin subjects until we have enough questions
    while len(questions) < num_questions and subjects:
        for subject in subjects:
            if len(questions) >= num_questions:
                break
            nodes = list(
                ContentNode.objects.filter(
                    tenant=tenant, subject=subject,
                    node_type__in=['topic', 'section'],
                ).order_by('?')[:3]
            )
            if not nodes:
                continue
            node = rng.choice(nodes)

            # Try LLM, fall back to stub on any failure
            try:
                generated = generator.generate_questions(
                    topic=node.title, difficulty='medium', count=1,
                    question_type='mcq', subject_context=subject.name,
                )
                if generated and generated[0].get('question'):
                    q = generated[0]
                    questions.append({
                        'id': len(questions),
                        'subject_id': subject.id,
                        'subject_name': subject.name,
                        'node_id': node.id,
                        'question': q['question'],
                        'options': q['options'],
                        'correct_answer': q['correct_answer'],
                    })
                    continue
            except Exception as exc:
                logger.info('Aptitude LLM fallback for node %s: %s', node.id, exc)

            # Fallback: canned stub
            canned = _canned_mcq(node, subject)
            questions.append({
                'id': len(questions),
                'subject_id': subject.id,
                'subject_name': subject.name,
                'node_id': node.id,
                'question': canned['question'],
                'options': canned['options'],
                'correct_answer': canned['correct_answer'],
            })
        # If we exhausted subjects and still don't have enough, stop
        if len(questions) == 0:
            break

    return questions


def grade_aptitude_responses(
    questions: List[Dict], responses: List[Dict],
) -> Dict[int, Tuple[int, int]]:
    """Tally correct/total per subject_id.

    responses items: {id, selected}
    Returns: {subject_id: (correct_count, total_count)}.
    """
    by_id = {q['id']: q for q in questions}
    tally: Dict[int, List[int]] = {}  # subject_id -> [correct, total]
    for r in responses:
        q = by_id.get(r.get('id'))
        if not q:
            continue
        bucket = tally.setdefault(q['subject_id'], [0, 0])
        bucket[1] += 1
        if (r.get('selected') or '').strip() == (q.get('correct_answer') or '').strip():
            bucket[0] += 1
    return {sid: (c, t) for sid, (c, t) in tally.items()}
