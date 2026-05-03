"""Calibrated rank computation from per-subject aptitude results."""

from typing import Dict, Tuple


def calibrated_rank(overall_accuracy: float) -> str:
    if overall_accuracy >= 0.85:
        return 'C'
    if overall_accuracy >= 0.70:
        return 'D'
    return 'E'


def apply_calibration(student, tally: Dict[int, Tuple[int, int]]) -> str:
    """Write per-subject mastery to profile. Return calibrated rank letter.

    `tally` shape: {subject_id: (correct, total)}.
    """
    from apps.service.models import StudentProfile

    profile, _ = StudentProfile.objects.get_or_create(student=student)

    mastery = {}
    total_correct = 0
    total_total = 0
    for sid, (c, t) in tally.items():
        if t <= 0:
            continue
        mastery[str(sid)] = int(round(c / t * 100))
        total_correct += c
        total_total += t

    profile.mastery_per_subject = mastery
    profile.save(update_fields=['mastery_per_subject', 'updated_at'])

    overall = (total_correct / total_total) if total_total else 0.0
    return calibrated_rank(overall)
