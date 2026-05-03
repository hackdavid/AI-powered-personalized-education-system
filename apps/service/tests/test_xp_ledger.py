"""Tests for the XP ledger service (Phase B)."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Role, Tenant, User
from apps.service.models import StudentProfile, XPLedger
from apps.service.services.xp import award_xp, get_recent_xp_events


def _ensure_roles():
    Role.objects.get_or_create(
        name=Role.STUDENT, defaults={'display_name': 'Student', 'level': 100},
    )


class AwardXPBasicsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _ensure_roles()
        cls.tenant = Tenant.objects.create(name='XP School', slug='xp')
        cls.role = Role.objects.get(name=Role.STUDENT)

    def _student(self, email='xp1@t.test'):
        u = User.objects.create_user(
            email=email, password='p', first_name='X', last_name='P',
            tenant=self.tenant, role=self.role, is_active=True, grade_level=8,
        )
        return u

    def test_award_creates_ledger_row_and_bumps_profile(self):
        u = self._student()
        res = award_xp(u, XPLedger.SOURCE_QUEST, 100, description='test')
        self.assertEqual(res.awarded, 100)
        self.assertEqual(res.requested, 100)
        self.assertFalse(res.capped)

        u.profile.refresh_from_db()
        self.assertEqual(u.profile.total_xp, 100)

        ledger = XPLedger.objects.filter(student=u)
        self.assertEqual(ledger.count(), 1)
        self.assertEqual(ledger.first().amount, 100)
        self.assertEqual(ledger.first().source, XPLedger.SOURCE_QUEST)

    def test_level_up_on_crossing_threshold(self):
        u = self._student()
        # Level 2 needs xp_for_level(2) = int(100 * 2**1.5) ~= 282
        res = award_xp(u, XPLedger.SOURCE_QUEST, 300, ignore_cap=True)
        self.assertTrue(res.leveled_up)
        u.profile.refresh_from_db()
        self.assertGreaterEqual(u.profile.level, 2)

    def test_rank_up_when_level_crosses_rank_boundary(self):
        u = self._student()
        # Jump to level 10 (rank D) by dumping a huge XP with ignore_cap
        # xp_for_level(10) = int(100 * 10**1.5) = 3162
        res = award_xp(u, XPLedger.SOURCE_ADMIN_ADJUSTMENT, 3500, ignore_cap=True)
        self.assertTrue(res.leveled_up)
        self.assertTrue(res.ranked_up)
        self.assertEqual(res.new_rank, StudentProfile.RANK_D)

    def test_daily_cap_clamps_second_award(self):
        u = self._student()
        r1 = award_xp(u, XPLedger.SOURCE_QUEST, 500)
        self.assertEqual(r1.awarded, 500)

        r2 = award_xp(u, XPLedger.SOURCE_QUEST, 600)
        self.assertEqual(r2.awarded, 500)      # only 500 remaining
        self.assertTrue(r2.capped)
        self.assertEqual(r2.requested, 600)

        # Third award should be fully capped (0 awarded, still capped)
        r3 = award_xp(u, XPLedger.SOURCE_QUEST, 100)
        self.assertEqual(r3.awarded, 0)
        self.assertTrue(r3.capped)
        # No ledger row when nothing was actually awarded
        self.assertEqual(
            XPLedger.objects.filter(student=u, amount=0).count(), 0,
        )

        u.profile.refresh_from_db()
        self.assertEqual(u.profile.daily_xp_earned, StudentProfile.DAILY_XP_CAP)

    def test_ignore_cap_bypasses_daily_cap(self):
        u = self._student()
        award_xp(u, XPLedger.SOURCE_QUEST, 900)
        res = award_xp(u, XPLedger.SOURCE_ADMIN_ADJUSTMENT, 500, ignore_cap=True)
        self.assertEqual(res.awarded, 500)
        self.assertFalse(res.capped)
        u.profile.refresh_from_db()
        self.assertEqual(u.profile.total_xp, 1400)

    def test_new_day_reset_clears_daily_counter(self):
        u = self._student()
        award_xp(u, XPLedger.SOURCE_QUEST, 800)
        u.profile.refresh_from_db()
        # Simulate yesterday's reset date
        u.profile.daily_xp_reset_date = timezone.localdate() - timedelta(days=1)
        u.profile.save(update_fields=['daily_xp_reset_date'])

        res = award_xp(u, XPLedger.SOURCE_QUEST, 900)
        # Should not be capped — it's a new day.
        self.assertEqual(res.awarded, 900)
        self.assertFalse(res.capped)
        u.profile.refresh_from_db()
        self.assertEqual(u.profile.daily_xp_earned, 900)
        self.assertEqual(u.profile.daily_xp_reset_date, timezone.localdate())

    def test_negative_amount_not_below_zero(self):
        u = self._student()
        award_xp(u, XPLedger.SOURCE_QUEST, 100)
        res = award_xp(u, XPLedger.SOURCE_ADMIN_ADJUSTMENT, -500)
        self.assertEqual(res.awarded, -500)
        u.profile.refresh_from_db()
        self.assertEqual(u.profile.total_xp, 0)     # floored at 0

    def test_get_recent_xp_events(self):
        u = self._student()
        award_xp(u, XPLedger.SOURCE_QUEST, 10)
        award_xp(u, XPLedger.SOURCE_HUNT_TASK, 20)
        award_xp(u, XPLedger.SOURCE_DAILY_QUEST, 30)
        events = get_recent_xp_events(u, limit=10)
        self.assertEqual(len(events), 3)
        # Most recent first
        self.assertEqual(events[0].amount, 30)
