"""Tests for the student Hunter profile page (/student/profile/)."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, Tenant, User
from apps.service.models import (
    Assignment, Class, Goal, StudentAssignment, StudentProfile, Subject, XPLedger,
)


def _ensure_roles():
    Role.objects.get_or_create(
        name=Role.STUDENT, defaults={'display_name': 'Student', 'level': 100})
    Role.objects.get_or_create(
        name=Role.TEACHER, defaults={'display_name': 'Teacher', 'level': 50})


class ProfileViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _ensure_roles()
        cls.tenant = Tenant.objects.create(name='Profile Test', slug='profile')
        cls.student_role = Role.objects.get(name=Role.STUDENT)
        cls.math = Subject.objects.create(
            tenant=cls.tenant, code='MATH', name='Mathematics')
        cls.science = Subject.objects.create(
            tenant=cls.tenant, code='SCI', name='Science')

    def _student(self, email='p@profile.test', onboarded=True, **profile_kwargs):
        u = User.objects.create_user(
            email=email, password='p', first_name='Pro', last_name='File',
            tenant=self.tenant, role=self.student_role,
            is_active=True, grade_level=8,
        )
        StudentProfile.objects.create(
            student=u, onboarding_complete=onboarded, **profile_kwargs,
        )
        return u

    # --- auth / gating ---------------------------------------------------

    def test_profile_requires_login(self):
        resp = self.client.get(reverse('student:profile'))
        self.assertEqual(resp.status_code, 302)
        # Should bounce to /auth/login (not to awakening — anonymous users
        # are handled by login_required, not the onboarding middleware).
        self.assertIn('/auth/login', resp.url)

    def test_profile_returns_200_for_onboarded_student(self):
        u = self._student(email='ok@profile.test')
        self.client.force_login(u)
        resp = self.client.get(reverse('student:profile'))
        self.assertEqual(resp.status_code, 200)
        # Identity shows the student's full name (or email fallback).
        self.assertContains(resp, u.get_full_name())

    def test_profile_respects_onboarding_wall(self):
        u = self._student(email='wall@profile.test', onboarded=False)
        self.client.force_login(u)
        resp = self.client.get(reverse('student:profile'), follow=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/student/awakening', resp.url)

    # --- stats rendering -------------------------------------------------

    def test_profile_shows_rank_level_xp(self):
        u = self._student(
            email='stats@profile.test',
            rank=StudentProfile.RANK_D, level=5, total_xp=1234,
        )
        self.client.force_login(u)
        resp = self.client.get(reverse('student:profile'))
        self.assertEqual(resp.status_code, 200)
        # Rank + level + total XP all appear in the rendered HTML.
        self.assertContains(resp, 'D')
        self.assertContains(resp, '5')
        self.assertContains(resp, '1234')

    # --- XP history ------------------------------------------------------

    def test_profile_renders_xp_history(self):
        u = self._student(email='xp@profile.test')
        XPLedger.objects.create(
            student=u, source=XPLedger.SOURCE_QUEST,
            amount=50, description='Cleared Algebra basics quest',
        )
        XPLedger.objects.create(
            student=u, source=XPLedger.SOURCE_HUNT_TASK,
            amount=25, description='Completed hunt task: geometry',
        )
        XPLedger.objects.create(
            student=u, source=XPLedger.SOURCE_AWAKENING,
            amount=100, description='Awakening calibration reward',
        )
        self.client.force_login(u)
        resp = self.client.get(reverse('student:profile'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Cleared Algebra basics quest')
        self.assertContains(resp, 'Completed hunt task: geometry')
        self.assertContains(resp, 'Awakening calibration reward')

    # --- mastery ---------------------------------------------------------

    def test_profile_renders_mastery(self):
        u = self._student(
            email='mastery@profile.test',
            mastery_per_subject={
                str(self.math.id): 70,
                str(self.science.id): 50,
            },
        )
        self.client.force_login(u)
        resp = self.client.get(reverse('student:profile'))
        self.assertEqual(resp.status_code, 200)
        # Both pct values should appear.
        self.assertContains(resp, '70')
        self.assertContains(resp, '50')
        # Subject names resolved from the mastery map.
        self.assertContains(resp, 'Mathematics')
        self.assertContains(resp, 'Science')

    # --- journey counts --------------------------------------------------

    def test_profile_renders_journey_counts(self):
        u = self._student(email='journey@profile.test')

        # 1 completed Hunt
        Goal.objects.create(
            student=u, title='Cleared hunt',
            target_date=timezone.localdate() + timedelta(days=5),
            status=Goal.STATUS_COMPLETED,
        )

        # 1 graded StudentAssignment
        cls_ = Class.objects.create(
            tenant=self.tenant, name='G8A', grade_level=8, section='A',
            academic_year='2025-2026',
        )
        assignment = Assignment.objects.create(
            tenant=self.tenant, class_obj=cls_, subject=self.math,
            title='Quest 1', description='',
            due_date=timezone.now() + timedelta(days=1),
            total_marks=10, difficulty=2, reward_xp=50,
            status=Assignment.STATUS_PUBLISHED, published_at=timezone.now(),
        )
        StudentAssignment.objects.create(
            student=u, assignment=assignment,
            status=StudentAssignment.STATUS_GRADED,
            score=8, max_score=10, graded_at=timezone.now(),
        )

        self.client.force_login(u)
        resp = self.client.get(reverse('student:profile'))
        self.assertEqual(resp.status_code, 200)

        # Counts surface in context + HTML.
        self.assertEqual(resp.context['hunts_completed'], 1)
        self.assertEqual(resp.context['quests_graded'], 1)
        # avg = 80% — the number should appear in the output.
        self.assertEqual(resp.context['avg_quest_pct'], 80)
        self.assertContains(resp, 'Hunts Cleared')
        self.assertContains(resp, 'Quests Graded')
        self.assertContains(resp, '80%')
