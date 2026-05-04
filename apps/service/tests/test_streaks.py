"""Tests for the streak engine (apps.service.services.streaks)."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Role, Tenant, User
from apps.service.models import StudentProfile, XPLedger
from apps.service.services.streaks import (
    STREAK_MILESTONES,
    recompute_streak,
)


def _ensure_roles():
    Role.objects.get_or_create(
        name=Role.STUDENT,
        defaults={'display_name': 'Student', 'level': 100},
    )


def _xp_on(student, d, amount=10, source=XPLedger.SOURCE_QUEST):
    """Create an XPLedger row whose `created_at.date()` equals `d`.

    `auto_now_add` would otherwise stamp the row with "now"; we force the
    date via a raw UPDATE so the engine's per-day existence check sees the
    row where the test expects. We pick noon to avoid timezone rollover
    weirdness.
    """
    row = XPLedger.objects.create(
        student=student, source=source, amount=amount, description='test',
    )
    tz = timezone.get_current_timezone()
    stamp = timezone.make_aware(
        timezone.datetime.combine(
            d, timezone.datetime.min.time().replace(hour=12),
        ),
        tz,
    )
    XPLedger.objects.filter(pk=row.pk).update(created_at=stamp)
    return row


class StreakEngineTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _ensure_roles()
        cls.tenant = Tenant.objects.create(name='Streak Tenant', slug='streak')
        cls.role = Role.objects.get(name=Role.STUDENT)

    def _student(self, email='streak@t.test'):
        u = User.objects.create_user(
            email=email, password='p', first_name='S', last_name='K',
            tenant=self.tenant, role=self.role, is_active=True, grade_level=8,
        )
        p = StudentProfile.objects.create(
            student=u, onboarding_complete=True,
        )
        return u, p

    # ---------------------------------------------------------------- core

    def test_five_consecutive_days(self):
        u, p = self._student()
        today = timezone.localdate()
        for offset in range(5):  # today, -1, -2, -3, -4
            _xp_on(u, today - timedelta(days=offset))
        result = recompute_streak(p)
        p.refresh_from_db()
        self.assertTrue(result['ran'])
        self.assertEqual(p.streak_days, 5)
        self.assertEqual(result['milestones_fired'], [])
        # No milestone below 7 days.
        self.assertEqual(
            XPLedger.objects.filter(
                student=u, source=XPLedger.SOURCE_STREAK_MILESTONE,
            ).count(),
            0,
        )

    def test_seven_day_milestone(self):
        u, p = self._student('7@t.test')
        today = timezone.localdate()
        for offset in range(7):
            _xp_on(u, today - timedelta(days=offset))
        result = recompute_streak(p)
        p.refresh_from_db()
        self.assertEqual(p.streak_days, 7)
        self.assertEqual(result['milestones_fired'], [7])

        milestone_rows = XPLedger.objects.filter(
            student=u, source=XPLedger.SOURCE_STREAK_MILESTONE,
        )
        self.assertEqual(milestone_rows.count(), 1)
        self.assertEqual(milestone_rows.first().amount, 100)
        self.assertIn(7, p.preferences.get('streak_milestones_hit', []))

    def test_thirty_day_milestone_includes_seven(self):
        u, p = self._student('30@t.test')
        today = timezone.localdate()
        for offset in range(30):
            _xp_on(u, today - timedelta(days=offset))
        result = recompute_streak(p)
        p.refresh_from_db()
        self.assertEqual(p.streak_days, 30)
        self.assertIn(7, result['milestones_fired'])
        self.assertIn(30, result['milestones_fired'])

        milestone_rows = XPLedger.objects.filter(
            student=u, source=XPLedger.SOURCE_STREAK_MILESTONE,
        )
        self.assertEqual(milestone_rows.count(), 2)
        total = sum(r.amount for r in milestone_rows)
        self.assertEqual(total, STREAK_MILESTONES[7] + STREAK_MILESTONES[30])
        self.assertEqual(total, 600)

    # --------------------------------------------------------- shield path

    def test_one_day_gap_shield_preserves(self):
        """XP on days 0, -1, then a gap on -2, then -3, -4, -5, -6. Shields=1
        lets the chain bridge the single gap. Streak = 6 active days."""
        u, p = self._student('gap@t.test')
        today = timezone.localdate()
        for offset in [0, 1, 3, 4, 5, 6]:
            _xp_on(u, today - timedelta(days=offset))
        p.streak_shields_remaining = 1
        # Prevent the weekly refill path from bumping shields back to 1
        # before we check the final count.
        p.last_shield_refill_date = today
        p.save(update_fields=[
            'streak_shields_remaining', 'last_shield_refill_date',
        ])
        recompute_streak(p)
        p.refresh_from_db()
        self.assertEqual(p.streak_days, 6)
        self.assertEqual(p.streak_shields_remaining, 0)

    def test_two_day_gap_resets(self):
        u, p = self._student('2gap@t.test')
        today = timezone.localdate()
        # Active: 0, -1, then 2-day gap (-2, -3), then -4, -5.
        for offset in [0, 1, 4, 5]:
            _xp_on(u, today - timedelta(days=offset))
        p.streak_shields_remaining = 0
        p.last_shield_refill_date = today
        p.save(update_fields=[
            'streak_shields_remaining', 'last_shield_refill_date',
        ])
        recompute_streak(p)
        p.refresh_from_db()
        # today + yesterday count, day -2 is missed with no shield → chain ends.
        self.assertEqual(p.streak_days, 2)
        self.assertEqual(p.streak_shields_remaining, 0)

    # --------------------------------------------------------- idempotence

    def test_same_day_second_call_is_noop(self):
        u, p = self._student('idem@t.test')
        today = timezone.localdate()
        _xp_on(u, today)
        first = recompute_streak(p)
        self.assertTrue(first['ran'])
        xp_count_after_first = XPLedger.objects.filter(student=u).count()

        second = recompute_streak(p)
        self.assertFalse(second['ran'])
        self.assertEqual(
            XPLedger.objects.filter(student=u).count(), xp_count_after_first,
        )

    # --------------------------------------------------------- shield refill

    def test_weekly_shield_refill(self):
        u, p = self._student('refill@t.test')
        today = timezone.localdate()
        last_week_monday = (
            today - timedelta(days=today.weekday()) - timedelta(days=7)
        )
        p.last_shield_refill_date = last_week_monday
        p.streak_shields_remaining = 0
        p.save(update_fields=[
            'last_shield_refill_date', 'streak_shields_remaining',
        ])
        recompute_streak(p)
        p.refresh_from_db()
        self.assertEqual(p.streak_shields_remaining, 1)
        self.assertEqual(p.last_shield_refill_date, today)

    # --------------------------------------------------------- milestones

    def test_milestone_does_not_refire(self):
        u, p = self._student('once@t.test')
        today = timezone.localdate()
        for offset in range(7):
            _xp_on(u, today - timedelta(days=offset))
        p.preferences = {'streak_milestones_hit': [7]}
        p.save(update_fields=['preferences'])

        result = recompute_streak(p)
        self.assertNotIn(7, result['milestones_fired'])
        self.assertEqual(
            XPLedger.objects.filter(
                student=u, source=XPLedger.SOURCE_STREAK_MILESTONE,
            ).count(),
            0,
        )

    # --------------------------------------------------------- today-no-xp

    def test_today_without_xp_does_not_reset(self):
        u, p = self._student('today@t.test')
        today = timezone.localdate()
        # No XP today. XP yesterday, day-before, and -3.
        for offset in [1, 2, 3]:
            _xp_on(u, today - timedelta(days=offset))
        p.streak_shields_remaining = 0
        p.last_shield_refill_date = today
        p.save(update_fields=[
            'streak_shields_remaining', 'last_shield_refill_date',
        ])
        recompute_streak(p)
        p.refresh_from_db()
        self.assertEqual(p.streak_days, 3)
