"""
User seeding for synthetic data.

Generates school admin + teachers + students per tenant using faker.
Idempotent on email; re-running with the same RNG seed produces the
same users so tests can rely on stable identities.
"""

import os
import random
from typing import Dict, List

from apps.accounts.models import Role, Tenant, User


DEFAULT_PASSWORD = os.environ.get('SEED_DEFAULT_PASSWORD', 'Test@1234')

PER_TENANT_TEACHERS = 10
PER_TENANT_STUDENTS = 80

# Grades 8 & 9 with sections A & B = 4 classes per tenant. Students are
# distributed evenly across them in `seed_users`. Adjust here if the
# default grade range changes.
DEFAULT_GRADE_LEVELS = [8, 9]
DEFAULT_SECTIONS = ['A', 'B']

TEACHER_SPECIALIZATIONS = [
    'Mathematics', 'Science', 'English', 'History',
    'Geography', 'Computer Science', 'Physical Education',
]


def _make_email(first: str, last: str, tenant_slug: str, idx: int = 0) -> str:
    base = f"{first}.{last}".lower().replace("'", '').replace(' ', '')
    suffix = f".{idx}" if idx else ''
    return f"{base}{suffix}@{tenant_slug}.test"


def _ensure_user(
    email: str,
    first: str,
    last: str,
    tenant: Tenant,
    role: Role,
    extra: Dict | None = None,
) -> tuple[User, bool]:
    extra = extra or {}
    user, created = User.objects.get_or_create(
        email=email,
        defaults={
            'first_name': first,
            'last_name': last,
            'tenant': tenant,
            'role': role,
            'is_active': True,
            'is_verified': True,
            **extra,
        },
    )
    if created:
        user.set_password(DEFAULT_PASSWORD)
        user.save(update_fields=['password'])
    return user, created


def seed_users(
    tenant: Tenant,
    seed: int = 42,
    teachers_count: int = PER_TENANT_TEACHERS,
    students_count: int = PER_TENANT_STUDENTS,
) -> Dict:
    """
    Seed users for a tenant.

    Returns a dict with the created/looked-up Role buckets so downstream
    seeders (classes, books, submissions) can pick teachers and students
    without re-querying.
    """
    from faker import Faker

    fake = Faker()
    Faker.seed(seed)
    rng = random.Random(seed)

    role_school_admin = Role.objects.get(name=Role.SCHOOL_ADMIN)
    role_teacher = Role.objects.get(name=Role.TEACHER)
    role_student = Role.objects.get(name=Role.STUDENT)

    summary = {
        'school_admins': [],
        'teachers': [],
        'students': [],
        'created': {'school_admins': 0, 'teachers': 0, 'students': 0},
    }

    # 1. School admin (one per tenant, deterministic email)
    sa_email = f'admin@{tenant.slug}.test'
    sa, created = _ensure_user(
        sa_email,
        first='School',
        last='Admin',
        tenant=tenant,
        role=role_school_admin,
        extra={'employee_id': f'SA-{tenant.slug.upper()}-001'},
    )
    summary['school_admins'].append(sa)
    summary['created']['school_admins'] += int(created)

    # 2. Teachers
    for i in range(teachers_count):
        first = fake.first_name()
        last = fake.last_name()
        email = _make_email(first, last, tenant.slug, idx=i)
        spec = TEACHER_SPECIALIZATIONS[i % len(TEACHER_SPECIALIZATIONS)]
        t, created = _ensure_user(
            email, first, last, tenant, role_teacher,
            extra={
                'employee_id': f'T-{tenant.slug.upper()}-{i+1:03d}',
                'specialization': spec,
                'phone': fake.phone_number()[:20],
            },
        )
        summary['teachers'].append(t)
        summary['created']['teachers'] += int(created)

    # 3. Students - evenly distribute across grade levels
    grades = DEFAULT_GRADE_LEVELS
    for i in range(students_count):
        first = fake.first_name()
        last = fake.last_name()
        email = _make_email(first, last, tenant.slug, idx=i)
        grade = grades[i % len(grades)]
        s, created = _ensure_user(
            email, first, last, tenant, role_student,
            extra={
                'student_id': f'S-{tenant.slug.upper()}-{i+1:04d}',
                'grade_level': grade,
            },
        )
        summary['students'].append(s)
        summary['created']['students'] += int(created)

    return summary


def reset_tenant_users(tenant: Tenant) -> dict:
    """
    Delete student / teacher / school_admin users for this tenant.
    Skips system_admins (they aren't tenant-scoped) and Django superusers.
    """
    qs = User.objects.filter(
        tenant=tenant,
        is_superuser=False,
        role__name__in=[Role.STUDENT, Role.TEACHER, Role.SCHOOL_ADMIN],
    )
    count = qs.count()
    qs.delete()
    return {'users_deleted': count}
