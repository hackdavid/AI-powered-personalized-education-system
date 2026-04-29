"""
Subject + Class + ClassSubject seeding for synthetic data.

Idempotent: keyed on `(tenant, code)` for Subject and
`(tenant, grade_level, section, academic_year)` for Class.
"""

import datetime
from typing import Dict, Iterable, List

from apps.accounts.models import Tenant, User
from apps.service.models import Class, ClassSubject, Subject


# Default subject palette (used when callers don't supply explicit subjects).
# Synced with TEACHER_SPECIALIZATIONS in users.py so the round-robin
# teacher-to-subject mapping makes some sense.
DEFAULT_SUBJECTS = [
    {'code': 'MATH', 'name': 'Mathematics', 'color': '#6366F1', 'icon': 'calculator'},
    {'code': 'SCI', 'name': 'Science', 'color': '#10B981', 'icon': 'beaker'},
    {'code': 'ENG', 'name': 'English', 'color': '#F59E0B', 'icon': 'book'},
    {'code': 'HIST', 'name': 'History', 'color': '#EF4444', 'icon': 'globe'},
    {'code': 'GEO', 'name': 'Geography', 'color': '#3B82F6', 'icon': 'map'},
]


DEFAULT_GRADE_LEVELS = [8, 9]
DEFAULT_SECTIONS = ['A', 'B']


def _academic_year(today: datetime.date | None = None) -> str:
    """E.g. 2026-2027 if August 2026, otherwise 2025-2026."""
    today = today or datetime.date.today()
    if today.month >= 7:
        return f"{today.year}-{today.year + 1}"
    return f"{today.year - 1}-{today.year}"


def seed_subjects(tenant: Tenant, subjects: Iterable[Dict] = None) -> Dict[str, Subject]:
    """
    Create Subject rows for a tenant. Returns a {code: Subject} map for
    downstream lookups (used by books.py).
    """
    subjects = list(subjects) if subjects else DEFAULT_SUBJECTS
    out: Dict[str, Subject] = {}
    for spec in subjects:
        subject, _ = Subject.objects.get_or_create(
            tenant=tenant,
            code=spec['code'],
            defaults={
                'name': spec['name'],
                'color': spec.get('color', '#6366F1'),
                'icon': spec.get('icon', ''),
                'description': spec.get('description', ''),
                'is_active': True,
            },
        )
        out[spec['code']] = subject
    return out


def seed_classes(
    tenant: Tenant,
    teachers: List[User],
    grades: Iterable[int] = None,
    sections: Iterable[str] = None,
    academic_year: str | None = None,
) -> List[Class]:
    """
    Create Class rows for the cartesian product of grades x sections.
    Round-robins class teachers from `teachers`.
    """
    grades = list(grades) if grades else DEFAULT_GRADE_LEVELS
    sections = list(sections) if sections else DEFAULT_SECTIONS
    year = academic_year or _academic_year()

    out: List[Class] = []
    teacher_pool = teachers or []
    counter = 0
    for grade in grades:
        for section in sections:
            class_teacher = teacher_pool[counter % len(teacher_pool)] if teacher_pool else None
            counter += 1
            cls, _ = Class.objects.get_or_create(
                tenant=tenant,
                grade_level=grade,
                section=section,
                academic_year=year,
                defaults={
                    'name': f'Grade {grade} - Section {section}',
                    'class_teacher': class_teacher,
                    'max_students': 40,
                    'is_active': True,
                },
            )
            out.append(cls)
    return out


def seed_class_subjects(
    classes: List[Class],
    subjects_by_code: Dict[str, Subject],
    teachers: List[User],
) -> List[ClassSubject]:
    """
    Wire every class to every subject with a teacher round-robin.
    Idempotent on `(class_obj, subject)`.
    """
    out: List[ClassSubject] = []
    if not teachers:
        teachers = [None]  # allow seeding without teachers (will leave teacher=None)
    counter = 0
    for cls in classes:
        for code, subject in subjects_by_code.items():
            teacher = teachers[counter % len(teachers)] if teachers else None
            counter += 1
            cs, _ = ClassSubject.objects.get_or_create(
                class_obj=cls,
                subject=subject,
                defaults={
                    'teacher': teacher,
                    'is_active': True,
                },
            )
            out.append(cs)
    return out
