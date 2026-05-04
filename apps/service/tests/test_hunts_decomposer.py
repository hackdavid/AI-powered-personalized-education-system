"""Tests for Hunt (Goal) decomposition service."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Role, Tenant, User
from apps.service.models import Goal, StudentProfile, Task
from apps.service.services.hunts import decompose_goal
from apps.service.services.hunts.decomposer import STUB_TEMPLATE


def _ensure_roles():
    Role.objects.get_or_create(
        name=Role.STUDENT, defaults={'display_name': 'Student', 'level': 100},
    )


class StubDecompositionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _ensure_roles()
        cls.tenant = Tenant.objects.create(name='Hunt School', slug='hunt')
        cls.role = Role.objects.get(name=Role.STUDENT)

    def _student(self, email='h@t.test'):
        u = User.objects.create_user(
            email=email, password='p', first_name='H', last_name='T',
            tenant=self.tenant, role=self.role,
            is_active=True, grade_level=8,
        )
        StudentProfile.objects.get_or_create(student=u)
        return u

    def _goal(self, student, **extra):
        return Goal.objects.create(
            student=student,
            title='Master Quadratics',
            description='Learn to solve quadratic equations',
            target_date=timezone.localdate() + timedelta(days=14),
            status=Goal.STATUS_ACTIVE,
            **extra,
        )

    @override_settings(OPENAI_API_KEY='')
    def test_stub_decomposition_creates_6_tasks(self):
        u = self._student()
        goal = self._goal(u)
        tasks = decompose_goal(goal)
        self.assertEqual(len(tasks), len(STUB_TEMPLATE))
        self.assertEqual(Task.objects.filter(goal=goal).count(), len(STUB_TEMPLATE))

    @override_settings(OPENAI_API_KEY='')
    def test_stub_decomposition_kinds_are_valid(self):
        u = self._student()
        goal = self._goal(u)
        tasks = decompose_goal(goal)
        valid_kinds = {k for k, _ in Task.KIND_CHOICES}
        for t in tasks:
            self.assertIn(t.kind, valid_kinds)

    @override_settings(OPENAI_API_KEY='')
    def test_decomposed_at_is_set(self):
        u = self._student()
        goal = self._goal(u)
        decompose_goal(goal)
        goal.refresh_from_db()
        self.assertIsNotNone(goal.decomposed_at)

    @override_settings(OPENAI_API_KEY='')
    def test_calling_again_without_force_is_idempotent(self):
        u = self._student()
        goal = self._goal(u)
        first = decompose_goal(goal)
        first_ids = {t.id for t in first}
        second = decompose_goal(goal)
        second_ids = {t.id for t in second}
        self.assertEqual(first_ids, second_ids)
        self.assertEqual(Task.objects.filter(goal=goal).count(), len(first))

    @override_settings(OPENAI_API_KEY='')
    def test_force_within_24h_raises(self):
        u = self._student()
        goal = self._goal(u)
        decompose_goal(goal)
        with self.assertRaises(ValueError):
            decompose_goal(goal, force=True)


class LLMMockedDecompositionTests(TestCase):
    """Ensure that when an LLM IS configured, the decomposer uses it via the
    service's `generate()` method. We mock the service so tests don't do
    actual network calls."""

    @classmethod
    def setUpTestData(cls):
        _ensure_roles()
        cls.tenant = Tenant.objects.create(name='LHunt School', slug='lhunt')
        cls.role = Role.objects.get(name=Role.STUDENT)

    def _student(self):
        u = User.objects.create_user(
            email='lh@t.test', password='p', first_name='L', last_name='H',
            tenant=self.tenant, role=self.role, is_active=True, grade_level=8,
        )
        StudentProfile.objects.get_or_create(student=u)
        return u

    def _goal(self, student):
        return Goal.objects.create(
            student=student,
            title='Master Quadratics',
            description='Learn to solve quadratic equations',
            target_date=timezone.localdate() + timedelta(days=14),
            status=Goal.STATUS_ACTIVE,
        )

    @override_settings(OPENAI_API_KEY='sk-test')
    @patch('clients.llm.LLMService.generate')
    def test_llm_path_used_when_configured(self, mock_generate):
        mock_generate.return_value = (
            '[{"title": "LLM Task 1", "description": "d", "kind": "read", '
            '"xp_reward": 20, "order": 0, "ref_node_id": null},'
            '{"title": "LLM Task 2", "description": "d2", "kind": "boss", '
            '"xp_reward": 60, "order": 1, "ref_node_id": null}]'
        )
        u = self._student()
        goal = self._goal(u)
        tasks = decompose_goal(goal)
        mock_generate.assert_called_once()
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0].title, 'LLM Task 1')
        self.assertEqual(tasks[1].kind, 'boss')

    @override_settings(OPENAI_API_KEY='sk-test')
    @patch('clients.llm.LLMService.generate')
    def test_llm_failure_falls_back_to_stub_cleanly(self, mock_generate):
        mock_generate.side_effect = RuntimeError('upstream 503')
        u = self._student()
        goal = self._goal(u)
        tasks = decompose_goal(goal)
        # Fallback to stub (6 tasks)
        self.assertEqual(len(tasks), len(STUB_TEMPLATE))
