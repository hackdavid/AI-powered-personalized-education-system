"""Tests for the Mission Brief generator service."""

from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Role, Tenant, User
from apps.service.models import MissionBrief, MissionItem, StudentProfile, Subject
from apps.service.services.missions import (
    ensure_todays_brief, generate_mission_brief, expire_old_briefs,
)


def _ensure_roles():
    Role.objects.get_or_create(name=Role.STUDENT, defaults={'display_name': 'Student', 'level': 100})


class MissionGeneratorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _ensure_roles()
        cls.tenant = Tenant.objects.create(name='Gen Test', slug='gen')
        cls.subject = Subject.objects.create(
            tenant=cls.tenant, code='MATH', name='Mathematics',
        )
        cls.role = Role.objects.get(name=Role.STUDENT)

    def _student(self, email='g@t.test', mastery=None, streak=0):
        u = User.objects.create_user(
            email=email, password='p', first_name='G', last_name='T',
            tenant=self.tenant, role=self.role, is_active=True, grade_level=8,
        )
        p = StudentProfile.objects.create(student=u, onboarding_complete=True)
        if mastery is not None:
            p.mastery_per_subject = mastery
        if streak:
            p.streak_days = streak
        p.save()
        return u

    def test_ensure_creates_brief_if_missing(self):
        u = self._student()
        brief = ensure_todays_brief(u)
        self.assertEqual(brief.date, timezone.localdate())
        self.assertGreaterEqual(brief.items.count(), 2)

    def test_ensure_is_idempotent(self):
        u = self._student()
        b1 = ensure_todays_brief(u)
        item_ids = set(b1.items.values_list('id', flat=True))
        b2 = ensure_todays_brief(u)
        self.assertEqual(b1.pk, b2.pk)
        self.assertEqual(set(b2.items.values_list('id', flat=True)), item_ids)

    def test_weakest_subject_item_is_generated(self):
        u = self._student(mastery={str(self.subject.id): 30})
        brief = ensure_todays_brief(u)
        titles = list(brief.items.values_list('title', flat=True))
        self.assertTrue(any('Mathematics' in t for t in titles))
        # Should also be the highest-priority item
        top = brief.items.order_by('-priority').first()
        self.assertIn('Mathematics', top.title)

    def test_streak_item_appears_when_streak_positive(self):
        u = self._student(streak=7)
        brief = ensure_todays_brief(u)
        kinds = list(brief.items.values_list('kind', flat=True))
        self.assertIn(MissionItem.KIND_STREAK, kinds)

    def test_streak_item_absent_when_streak_zero(self):
        u = self._student(streak=0)
        brief = ensure_todays_brief(u)
        kinds = list(brief.items.values_list('kind', flat=True))
        self.assertNotIn(MissionItem.KIND_STREAK, kinds)

    def test_expire_old_briefs_marks_items(self):
        u = self._student()
        yesterday = timezone.localdate() - timedelta(days=1)
        old_brief = MissionBrief.objects.create(student=u, date=yesterday)
        MissionItem.objects.create(
            brief=old_brief, title='Old', kind=MissionItem.KIND_CHAT,
            xp_reward=10,
        )
        count = expire_old_briefs(u, up_to_date=timezone.localdate())
        self.assertEqual(count, 1)
        self.assertEqual(
            old_brief.items.first().status, MissionItem.STATUS_EXPIRED,
        )

    def test_regenerate_clears_existing_items(self):
        u = self._student()
        brief = MissionBrief.objects.create(student=u, date=timezone.localdate())
        MissionItem.objects.create(
            brief=brief, title='ghost', kind=MissionItem.KIND_CHAT, xp_reward=1,
        )
        items = generate_mission_brief(brief)
        self.assertNotIn('ghost', [i.title for i in items])
        self.assertEqual(brief.items.filter(title='ghost').count(), 0)
