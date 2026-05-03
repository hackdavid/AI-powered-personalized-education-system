"""Tests for student hunt (Goal) views."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, Tenant, User
from apps.service.models import Goal, StudentProfile, Subject, Task


def _ensure_roles():
    Role.objects.get_or_create(
        name=Role.STUDENT, defaults={'display_name': 'Student', 'level': 100})


class HuntFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _ensure_roles()
        cls.tenant = Tenant.objects.create(name='Hunt Test', slug='hunt')
        cls.student_role = Role.objects.get(name=Role.STUDENT)
        cls.subject = Subject.objects.create(
            tenant=cls.tenant, code='MATH', name='Mathematics')

    def _student(self, email='h@hunt.test'):
        u = User.objects.create_user(
            email=email, password='p', first_name='H', last_name='X',
            tenant=self.tenant, role=self.student_role,
            is_active=True, grade_level=8,
        )
        StudentProfile.objects.create(student=u, onboarding_complete=True)
        return u

    def test_list_requires_login(self):
        resp = self.client.get(reverse('student:hunt_list'))
        self.assertEqual(resp.status_code, 302)

    def test_list_renders_empty(self):
        u = self._student()
        self.client.force_login(u)
        resp = self.client.get(reverse('student:hunt_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'NO HUNTS YET')

    def test_new_form_renders(self):
        u = self._student()
        self.client.force_login(u)
        resp = self.client.get(reverse('student:hunt_new'))
        self.assertEqual(resp.status_code, 200)

    def test_create_hunt_triggers_decomposition_and_persists_tasks(self):
        u = self._student()
        self.client.force_login(u)
        target = (timezone.localdate() + timedelta(days=14)).isoformat()
        with patch(
            'apps.web.views.student.hunts.decompose_goal',
            side_effect=lambda goal, force=False: [
                Task.objects.create(
                    goal=goal, order=i, title=f'Task {i}', kind='practice',
                    xp_reward=20,
                ) for i in range(5)
            ],
        ) as mock_decompose:
            resp = self.client.post(reverse('student:hunt_new'), {
                'title': 'Master polynomials',
                'description': 'Factoring + quadratics',
                'subject': self.subject.id,
                'target_date': target,
            })
        self.assertEqual(resp.status_code, 302)
        g = Goal.objects.get(student=u, title='Master polynomials')
        self.assertEqual(g.subject, self.subject)
        self.assertEqual(g.tasks.count(), 5)
        mock_decompose.assert_called_once()

    def test_create_hunt_past_date_rejected(self):
        u = self._student()
        self.client.force_login(u)
        past = (timezone.localdate() - timedelta(days=1)).isoformat()
        resp = self.client.post(reverse('student:hunt_new'), {
            'title': 'Past hunt', 'target_date': past,
        })
        # Renders form again with error, no redirect
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Goal.objects.filter(student=u).exists())

    def test_detail_renders_dungeon_map(self):
        u = self._student()
        g = Goal.objects.create(
            student=u, title='Hunt X',
            target_date=timezone.localdate() + timedelta(days=10),
        )
        Task.objects.create(goal=g, order=0, title='Read', kind='read', xp_reward=10)
        Task.objects.create(goal=g, order=1, title='Boss', kind='boss', xp_reward=50)
        self.client.force_login(u)
        resp = self.client.get(reverse('student:hunt_detail', args=[g.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Hunt X')
        self.assertContains(resp, 'Boss')

    def _canned_quiz(self, count=3):
        """Pre-populate quiz_questions to avoid LLM calls in tests."""
        return [
            {
                'question': f'Test question {i + 1}?',
                'options': [
                    {'key': 'A', 'text': 'Right answer'},
                    {'key': 'B', 'text': 'Wrong 1'},
                    {'key': 'C', 'text': 'Wrong 2'},
                    {'key': 'D', 'text': 'Wrong 3'},
                ],
                'correct_answer': 'A',
                'explanation': 'Because the test says so.',
            }
            for i in range(count)
        ]

    def test_task_quiz_get_renders_form(self):
        u = self._student()
        g = Goal.objects.create(
            student=u, title='Q Hunt',
            target_date=timezone.localdate() + timedelta(days=10),
        )
        t = Task.objects.create(
            goal=g, order=0, title='Solo', kind='read', xp_reward=10,
            quiz_questions=self._canned_quiz(3),
        )
        self.client.force_login(u)
        resp = self.client.get(reverse('student:hunt_task_quiz', args=[t.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Test question 1?')
        self.assertContains(resp, 'Test question 3?')

    def test_task_quiz_passing_awards_xp_and_clears_task(self):
        u = self._student()
        g = Goal.objects.create(
            student=u, title='XP Hunt',
            target_date=timezone.localdate() + timedelta(days=10),
        )
        t = Task.objects.create(
            goal=g, order=0, title='Solo', kind='practice', xp_reward=25,
            quiz_questions=self._canned_quiz(5),
        )
        self.client.force_login(u)
        # 5 correct answers — 100%, passes 60% threshold for practice kind
        resp = self.client.post(
            reverse('student:hunt_task_quiz', args=[t.id]),
            data={f'q_{i}': 'A' for i in range(5)},
        )
        self.assertEqual(resp.status_code, 200)
        t.refresh_from_db()
        self.assertTrue(t.is_completed)
        self.assertEqual(t.best_score_pct, 100)
        g.refresh_from_db()
        self.assertEqual(g.progress_pct, 100)
        self.assertEqual(g.status, Goal.STATUS_COMPLETED)
        u.refresh_from_db()
        self.assertGreaterEqual(u.profile.total_xp, 25)

    def test_task_quiz_failing_does_not_clear_task(self):
        u = self._student()
        g = Goal.objects.create(
            student=u, title='Fail Hunt',
            target_date=timezone.localdate() + timedelta(days=10),
        )
        t = Task.objects.create(
            goal=g, order=0, title='Solo', kind='read', xp_reward=10,
            quiz_questions=self._canned_quiz(3),
        )
        self.client.force_login(u)
        # All wrong answers (B) → 0% → below 67% threshold
        resp = self.client.post(
            reverse('student:hunt_task_quiz', args=[t.id]),
            data={f'q_{i}': 'B' for i in range(3)},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'NOT YET')
        t.refresh_from_db()
        self.assertFalse(t.is_completed)
        self.assertEqual(t.best_score_pct, 0)

    def test_task_quiz_best_score_tracked_across_attempts(self):
        u = self._student()
        g = Goal.objects.create(
            student=u, title='Best',
            target_date=timezone.localdate() + timedelta(days=10),
        )
        t = Task.objects.create(
            goal=g, order=0, title='Solo', kind='read', xp_reward=10,
            quiz_questions=self._canned_quiz(3),
        )
        self.client.force_login(u)
        # First attempt: 1/3 = 33%
        self.client.post(
            reverse('student:hunt_task_quiz', args=[t.id]),
            data={'q_0': 'A', 'q_1': 'B', 'q_2': 'B'},
        )
        t.refresh_from_db()
        self.assertEqual(t.best_score_pct, 33)
        # Second attempt: 2/3 = 67% → passes
        self.client.post(
            reverse('student:hunt_task_quiz', args=[t.id]),
            data={'q_0': 'A', 'q_1': 'A', 'q_2': 'B'},
        )
        t.refresh_from_db()
        self.assertEqual(t.best_score_pct, 67)
        self.assertTrue(t.is_completed)

    def test_task_quiz_already_completed_redirects(self):
        u = self._student()
        g = Goal.objects.create(
            student=u, title='Done',
            target_date=timezone.localdate() + timedelta(days=10),
        )
        t = Task.objects.create(
            goal=g, order=0, title='Solo', kind='read', xp_reward=10,
            is_completed=True, best_score_pct=80,
        )
        self.client.force_login(u)
        resp = self.client.get(reverse('student:hunt_task_quiz', args=[t.id]))
        self.assertEqual(resp.status_code, 302)

    def test_cannot_take_other_students_task_quiz(self):
        u = self._student('a@hunt.test')
        o = self._student('b@hunt.test')
        g = Goal.objects.create(
            student=u, title='Mine',
            target_date=timezone.localdate() + timedelta(days=5),
        )
        t = Task.objects.create(
            goal=g, order=0, title='t', kind='read', xp_reward=10,
            quiz_questions=self._canned_quiz(3),
        )
        self.client.force_login(o)
        resp = self.client.get(reverse('student:hunt_task_quiz', args=[t.id]))
        self.assertEqual(resp.status_code, 404)

    def test_required_questions_by_kind(self):
        u = self._student()
        g = Goal.objects.create(
            student=u, title='Kinds',
            target_date=timezone.localdate() + timedelta(days=10),
        )
        read_task = Task.objects.create(goal=g, order=0, title='r', kind='read', xp_reward=10)
        practice_task = Task.objects.create(goal=g, order=1, title='p', kind='practice', xp_reward=20)
        boss_task = Task.objects.create(goal=g, order=2, title='b', kind='boss', xp_reward=100)
        self.assertEqual(read_task.required_questions(), 3)
        self.assertEqual(practice_task.required_questions(), 5)
        self.assertEqual(boss_task.required_questions(), 10)
        self.assertEqual(read_task.pass_threshold_pct(), 67)
        self.assertEqual(boss_task.pass_threshold_pct(), 70)

    def test_abandon_hunt(self):
        u = self._student()
        g = Goal.objects.create(
            student=u, title='Doomed',
            target_date=timezone.localdate() + timedelta(days=3),
        )
        self.client.force_login(u)
        resp = self.client.post(reverse('student:hunt_abandon', args=[g.id]))
        self.assertEqual(resp.status_code, 302)
        g.refresh_from_db()
        self.assertEqual(g.status, Goal.STATUS_ABANDONED)
