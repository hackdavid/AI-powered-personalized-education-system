"""Tests for Phase A new models: StudentProfile, Enrollment, OnboardingResult,
MissionBrief, MissionItem."""

from datetime import date, timedelta

from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase

from apps.accounts.models import Role, Tenant, User
from apps.service.models import (
    Class,
    Enrollment,
    MissionBrief,
    MissionItem,
    OnboardingResult,
    StudentProfile,
)


def _ensure_roles():
    """Roles are created by migrations/seed; ensure they exist for tests."""
    Role.objects.get_or_create(name=Role.STUDENT, defaults={'display_name': 'Student', 'level': 100})
    Role.objects.get_or_create(name=Role.TEACHER, defaults={'display_name': 'Teacher', 'level': 50})


def _make_student(tenant, email='s@example.test', grade=8):
    _ensure_roles()
    role = Role.objects.get(name=Role.STUDENT)
    return User.objects.create_user(
        email=email, password='x', first_name='Test', last_name='Student',
        tenant=tenant, role=role, grade_level=grade, is_active=True,
    )


class StudentProfileTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='Test School', slug='test')

    def test_backfill_creates_profiles(self):
        s1 = _make_student(self.tenant, 's1@test.test')
        s2 = _make_student(self.tenant, 's2@test.test')
        call_command('backfill_student_profiles')
        self.assertTrue(StudentProfile.objects.filter(student=s1).exists())
        self.assertTrue(StudentProfile.objects.filter(student=s2).exists())
        self.assertFalse(StudentProfile.objects.get(student=s1).onboarding_complete)

    def test_xp_for_next_level_is_monotonic(self):
        s = _make_student(self.tenant)
        p = StudentProfile.objects.create(student=s)
        prev = 0
        for lvl in range(1, 20):
            p.level = lvl
            v = p.xp_for_next_level()
            self.assertGreater(v, prev)
            prev = v

    def test_recalculate_rank_boundaries(self):
        s = _make_student(self.tenant)
        p = StudentProfile.objects.create(student=s)
        cases = [(1, 'E'), (9, 'E'), (10, 'D'), (19, 'D'), (20, 'C'),
                 (34, 'C'), (35, 'B'), (54, 'B'), (55, 'A'), (79, 'A'),
                 (80, 'S'), (100, 'S')]
        for lvl, expected in cases:
            p.level = lvl
            self.assertEqual(p.recalculate_rank(), expected, f'level {lvl}')


class EnrollmentTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='Test School', slug='test')
        self.cls = Class.objects.create(
            tenant=self.tenant, name='Grade 8-A',
            grade_level=8, section='A', academic_year='2025-2026',
        )
        self.student = _make_student(self.tenant)

    def test_unique_class_student_pair(self):
        Enrollment.objects.create(class_obj=self.cls, student=self.student)
        with self.assertRaises(IntegrityError):
            Enrollment.objects.create(class_obj=self.cls, student=self.student)

    def test_m2m_students_reverse(self):
        Enrollment.objects.create(class_obj=self.cls, student=self.student)
        self.assertIn(self.student, self.cls.students.all())
        self.assertEqual(self.cls.student_count, 1)


class MissionTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='Test School', slug='test')
        self.student = _make_student(self.tenant)

    def test_mission_brief_unique_per_student_per_date(self):
        today = date.today()
        MissionBrief.objects.create(student=self.student, date=today)
        with self.assertRaises(IntegrityError):
            MissionBrief.objects.create(student=self.student, date=today)

    def test_mission_item_ordering_by_priority(self):
        brief = MissionBrief.objects.create(student=self.student, date=date.today())
        MissionItem.objects.create(brief=brief, title='A', kind='quest', priority=10)
        MissionItem.objects.create(brief=brief, title='B', kind='quest', priority=5)
        MissionItem.objects.create(brief=brief, title='C', kind='quest', priority=20)
        titles = list(brief.items.values_list('title', flat=True))
        self.assertEqual(titles, ['C', 'A', 'B'])

    def test_brief_auto_completes_when_all_items_done(self):
        brief = MissionBrief.objects.create(student=self.student, date=date.today())
        i1 = MissionItem.objects.create(brief=brief, title='x', kind='quest')
        i2 = MissionItem.objects.create(brief=brief, title='y', kind='chat')
        i1.mark_completed()
        brief.refresh_from_db()
        self.assertIsNone(brief.all_completed_at)
        i2.mark_completed()
        brief.refresh_from_db()
        self.assertIsNotNone(brief.all_completed_at)


class OnboardingResultTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name='Test School', slug='test')
        self.student = _make_student(self.tenant)

    def test_mark_complete_sets_step_and_timestamp(self):
        r = OnboardingResult.objects.create(student=self.student, current_step=5)
        r.mark_complete()
        r.refresh_from_db()
        self.assertEqual(r.current_step, OnboardingResult.STEP_COMPLETE)
        self.assertIsNotNone(r.completed_at)
