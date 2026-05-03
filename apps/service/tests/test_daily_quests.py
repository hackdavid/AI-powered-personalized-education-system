"""Tests for the DailyQuest generator (Phase B)."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Role, Tenant, User
from apps.service.models import DailyQuest, Goal, StudentProfile, Subject, Task
from apps.service.services.daily_quests import ensure_todays_daily_quests


def _ensure_roles():
    Role.objects.get_or_create(
        name=Role.STUDENT, defaults={'display_name': 'Student', 'level': 100},
    )


class DailyQuestTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _ensure_roles()
        cls.tenant = Tenant.objects.create(name='DQ School', slug='dq')
        cls.subject = Subject.objects.create(
            tenant=cls.tenant, code='MATH', name='Mathematics',
        )
        cls.role = Role.objects.get(name=Role.STUDENT)

    def _student(self, email='dq@t.test', mastery=None, streak=0):
        u = User.objects.create_user(
            email=email, password='p', first_name='D', last_name='Q',
            tenant=self.tenant, role=self.role, is_active=True, grade_level=8,
        )
        p, _ = StudentProfile.objects.get_or_create(student=u)
        if mastery is not None:
            p.mastery_per_subject = mastery
        if streak:
            p.streak_days = streak
        p.save()
        return u

    def test_creates_at_least_chat_visit(self):
        u = self._student()
        quests = ensure_todays_daily_quests(u)
        self.assertGreaterEqual(len(quests), 1)
        kinds = [q.kind for q in quests]
        self.assertIn(DailyQuest.KIND_VISIT_CHAT, kinds)

    def test_second_call_is_idempotent(self):
        u = self._student()
        first = ensure_todays_daily_quests(u)
        first_ids = {q.id for q in first}
        second = ensure_todays_daily_quests(u)
        second_ids = {q.id for q in second}
        # Same rows, no new ones
        self.assertEqual(first_ids, second_ids)
        today = timezone.localdate()
        self.assertEqual(
            DailyQuest.objects.filter(student=u, date=today).count(),
            len(first_ids),
        )

    def test_weakest_subject_quest_appears_when_mastery_present(self):
        u = self._student(mastery={str(self.subject.id): 20})
        quests = ensure_todays_daily_quests(u)
        kinds = [q.kind for q in quests]
        self.assertIn(DailyQuest.KIND_PRACTICE_WEAKEST, kinds)
        weak = next(q for q in quests if q.kind == DailyQuest.KIND_PRACTICE_WEAKEST)
        self.assertIn('Mathematics', weak.title)

    def test_hunt_quest_appears_when_active_hunt_with_tasks(self):
        u = self._student()
        # Create an active goal with a task
        g = Goal.objects.create(
            student=u, title='H', description='',
            target_date=timezone.localdate() + timedelta(days=14),
            status=Goal.STATUS_ACTIVE,
        )
        Task.objects.create(goal=g, order=0, title='t', kind=Task.KIND_READ)

        quests = ensure_todays_daily_quests(u)
        kinds = [q.kind for q in quests]
        self.assertIn(DailyQuest.KIND_HUNT_TASK, kinds)

    def test_hunt_quest_absent_when_no_active_hunt(self):
        u = self._student()
        quests = ensure_todays_daily_quests(u)
        kinds = [q.kind for q in quests]
        self.assertNotIn(DailyQuest.KIND_HUNT_TASK, kinds)

    def test_streak_quest_only_when_positive(self):
        # Zero streak — no streak quest
        u_zero = self._student(email='z@t.test', streak=0)
        kinds_zero = [q.kind for q in ensure_todays_daily_quests(u_zero)]
        self.assertNotIn(DailyQuest.KIND_STREAK, kinds_zero)

        # Positive streak — streak quest present
        u_streak = self._student(email='s@t.test', streak=5)
        kinds_streak = [q.kind for q in ensure_todays_daily_quests(u_streak)]
        self.assertIn(DailyQuest.KIND_STREAK, kinds_streak)
