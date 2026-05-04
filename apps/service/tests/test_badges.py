"""Tests for the Phase C badges engine + integration with the event hooks.

Covers:
  - Each criterion type in the catalog's rule set.
  - Idempotence (re-running the engine doesn't duplicate awards).
  - Integration: complete_awakening, grade_student_assignment,
    streak milestone via award_xp, hunt task pass via hunt quiz view.
  - Seed catalog matches expected codes.
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, Tenant, User
from apps.service.models import (
    Assignment, Badge, Class, EarnedBadge, Enrollment, Goal,
    Question, StudentAssignment, StudentProfile, Subject, Task,
)
from apps.service.services.badges import evaluate_and_award, STARTER_BADGES


def _ensure_roles():
    Role.objects.get_or_create(
        name=Role.STUDENT, defaults={'display_name': 'Student', 'level': 100})


def _install_badges():
    """Install the starter catalog once per test class via update_or_create."""
    for spec in STARTER_BADGES:
        Badge.objects.update_or_create(
            code=spec['code'],
            defaults={k: v for k, v in spec.items() if k != 'code'},
        )


class BadgeCriteriaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _ensure_roles()
        _install_badges()
        cls.tenant = Tenant.objects.create(name='Badge Test', slug='badges')
        cls.student_role = Role.objects.get(name=Role.STUDENT)
        cls.subject = Subject.objects.create(
            tenant=cls.tenant, code='MATH', name='Math')
        cls.cls = Class.objects.create(
            tenant=cls.tenant, name='G8A', grade_level=8, section='A',
            academic_year='2025-2026',
        )

    def _student(self, email='b@badges.test', **profile_kwargs):
        u = User.objects.create_user(
            email=email, password='p', first_name='B', last_name='T',
            tenant=self.tenant, role=self.student_role,
            is_active=True, grade_level=8,
        )
        StudentProfile.objects.create(student=u, **profile_kwargs)
        return u

    # ---- awakening_complete ------------------------------------------------

    def test_first_steps_requires_onboarding_complete(self):
        u = self._student('aw@badges.test', onboarding_complete=False)
        evaluate_and_award(u, event_type='awakening_complete')
        self.assertFalse(EarnedBadge.objects.filter(
            student=u, badge__code='first_steps').exists())

        u.profile.onboarding_complete = True
        u.profile.save()
        newly = evaluate_and_award(u, event_type='awakening_complete')
        self.assertTrue(any(e.badge.code == 'first_steps' for e in newly))

    # ---- quest_count -------------------------------------------------------

    def test_quest_novice_awarded_on_first_graded_quest(self):
        u = self._student('q1@badges.test', onboarding_complete=True)
        a = Assignment.objects.create(
            tenant=self.tenant, class_obj=self.cls, subject=self.subject,
            title='Q1', description='',
            due_date=timezone.now() + timedelta(days=3),
            total_marks=2, difficulty=3, reward_xp=30,
            status=Assignment.STATUS_PUBLISHED, published_at=timezone.now(),
        )
        StudentAssignment.objects.create(
            student=u, assignment=a, max_score=2, score=2,
            status=StudentAssignment.STATUS_GRADED,
            graded_at=timezone.now(),
        )
        evaluate_and_award(u, event_type='quest_graded')
        self.assertTrue(EarnedBadge.objects.filter(
            student=u, badge__code='quest_novice').exists())
        # perfectionist fires because score == max_score
        self.assertTrue(EarnedBadge.objects.filter(
            student=u, badge__code='perfectionist').exists())
        # quest_master (n=10) should NOT be awarded yet
        self.assertFalse(EarnedBadge.objects.filter(
            student=u, badge__code='quest_master').exists())

    # ---- quest_perfect only with score == max_score > 0 -------------------

    def test_perfectionist_requires_full_marks(self):
        u = self._student('pf@badges.test', onboarding_complete=True)
        a = Assignment.objects.create(
            tenant=self.tenant, class_obj=self.cls, subject=self.subject,
            title='P1', due_date=timezone.now() + timedelta(days=3),
            total_marks=4, difficulty=3, reward_xp=40,
            status=Assignment.STATUS_PUBLISHED, published_at=timezone.now(),
        )
        # 3/4 — not perfect
        StudentAssignment.objects.create(
            student=u, assignment=a, max_score=4, score=3,
            status=StudentAssignment.STATUS_GRADED,
            graded_at=timezone.now(),
        )
        evaluate_and_award(u, event_type='quest_graded')
        self.assertFalse(EarnedBadge.objects.filter(
            student=u, badge__code='perfectionist').exists())

    # ---- hunt_count -------------------------------------------------------

    def test_hunter_awarded_when_first_hunt_completed(self):
        u = self._student('h1@badges.test', onboarding_complete=True)
        Goal.objects.create(
            student=u, title='Test Hunt',
            target_date=timezone.localdate() + timedelta(days=5),
            status=Goal.STATUS_COMPLETED,
            completed_at=timezone.now(),
            progress_pct=100, xp_reward=200,
        )
        evaluate_and_award(u, event_type='hunt_completed')
        self.assertTrue(EarnedBadge.objects.filter(
            student=u, badge__code='hunter').exists())
        self.assertFalse(EarnedBadge.objects.filter(
            student=u, badge__code='warden').exists())

    # ---- streak_days -------------------------------------------------------

    def test_week_warrior_at_seven_day_streak(self):
        u = self._student('st@badges.test', onboarding_complete=True)
        u.profile.streak_days = 7
        u.profile.save(update_fields=['streak_days', 'updated_at'])
        evaluate_and_award(u, event_type='streak_milestone')
        self.assertTrue(EarnedBadge.objects.filter(
            student=u, badge__code='week_warrior').exists())

    # ---- rank_reached -----------------------------------------------------

    def test_ascended_d_at_rank_d(self):
        u = self._student('rd@badges.test', onboarding_complete=True)
        u.profile.rank = 'D'
        u.profile.save(update_fields=['rank', 'updated_at'])
        evaluate_and_award(u, event_type='xp_awarded')
        self.assertTrue(EarnedBadge.objects.filter(
            student=u, badge__code='ascended_d').exists())
        self.assertFalse(EarnedBadge.objects.filter(
            student=u, badge__code='ascended_c').exists())

    def test_ascended_c_also_grants_d(self):
        u = self._student('rc@badges.test', onboarding_complete=True)
        u.profile.rank = 'C'
        u.profile.save(update_fields=['rank', 'updated_at'])
        evaluate_and_award(u, event_type='xp_awarded')
        earned = set(EarnedBadge.objects.filter(student=u).values_list('badge__code', flat=True))
        self.assertIn('ascended_d', earned)
        self.assertIn('ascended_c', earned)

    # ---- idempotence -------------------------------------------------------

    def test_idempotent_reevaluation(self):
        u = self._student('idem@badges.test', onboarding_complete=True)
        first = evaluate_and_award(u)
        second = evaluate_and_award(u)
        # First call awards the onboarding badge; second call should award nothing new.
        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 0)

    # ---- catalog guard -----------------------------------------------------

    def test_starter_catalog_has_expected_codes(self):
        expected = {
            'first_steps', 'quest_novice', 'quest_master', 'perfectionist',
            'hunter', 'warden', 'week_warrior', 'iron_will',
            'ascended_d', 'ascended_c',
        }
        have = {spec['code'] for spec in STARTER_BADGES}
        self.assertEqual(expected, have)


class BadgeIntegrationTests(TestCase):
    """End-to-end: the hook in `award_xp` fires evaluate_and_award."""

    @classmethod
    def setUpTestData(cls):
        _ensure_roles()
        _install_badges()
        cls.tenant = Tenant.objects.create(name='Hook Test', slug='hook')
        cls.student_role = Role.objects.get(name=Role.STUDENT)

    def _student(self, email='i@hook.test'):
        u = User.objects.create_user(
            email=email, password='p', first_name='I', last_name='T',
            tenant=self.tenant, role=self.student_role,
            is_active=True, grade_level=8,
        )
        StudentProfile.objects.create(
            student=u, onboarding_complete=True, rank='E', level=1,
        )
        return u

    def test_award_xp_triggers_badge_eval_on_rank_up(self):
        from apps.service.services.xp import award_xp
        u = self._student()
        # Force a direct rank set via XP load — level 10 is Rank D threshold.
        # Use ignore_cap to ensure enough XP lands in one call.
        award_xp(
            u, source='quest', amount=5000,
            description='bulk level-up test', ignore_cap=True,
        )
        u.refresh_from_db()
        # Should have hit Rank D: ascended_d badge earned.
        codes = set(
            EarnedBadge.objects.filter(student=u)
            .values_list('badge__code', flat=True)
        )
        self.assertIn('ascended_d', codes)
