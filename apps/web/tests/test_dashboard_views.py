"""Tests for the data-driven student 'Status Window' dashboard.

The dashboard is mounted at `web:dashboard` (/dashboard/). `dashboard_router`
dispatches students into `_student_status_view` which assembles:
  * active_quest_count + overdue_quest_count
  * active_quest_rows (top 3)
  * active_hunt_rows (top 3)
  * streak_days (7-day grid)
  * mastery_rows, brief, items (untouched by this subagent)
and calls `recompute_streak(profile)` once per visit.
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, Tenant, User
from apps.service.models import (
    Assignment,
    Class,
    Enrollment,
    Goal,
    Question,
    StudentAssignment,
    StudentProfile,
    Subject,
)


def _ensure_roles():
    Role.objects.get_or_create(
        name=Role.STUDENT,
        defaults={'display_name': 'Student', 'level': 100},
    )
    Role.objects.get_or_create(
        name=Role.TEACHER,
        defaults={'display_name': 'Teacher', 'level': 50},
    )


class StudentStatusDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _ensure_roles()
        cls.tenant = Tenant.objects.create(name='Dash Test', slug='dash')
        cls.student_role = Role.objects.get(name=Role.STUDENT)
        cls.cls = Class.objects.create(
            tenant=cls.tenant, name='G8A', grade_level=8, section='A',
            academic_year='2025-2026',
        )
        cls.subject = Subject.objects.create(
            tenant=cls.tenant, code='MATH', name='Mathematics',
        )

    def _student(self, email='dash@t.test'):
        u = User.objects.create_user(
            email=email, password='p', first_name='D', last_name='A',
            tenant=self.tenant, role=self.student_role,
            is_active=True, grade_level=8,
        )
        StudentProfile.objects.create(student=u, onboarding_complete=True)
        Enrollment.objects.create(class_obj=self.cls, student=u)
        return u

    def _assignment(self, title='Q', due_in_hours=48, **extra):
        a = Assignment.objects.create(
            tenant=self.tenant, class_obj=self.cls, subject=self.subject,
            title=title, description='desc',
            due_date=timezone.now() + timedelta(hours=due_in_hours),
            total_marks=2, difficulty=3, reward_xp=40,
            status=Assignment.STATUS_PUBLISHED,
            published_at=timezone.now(),
            **extra,
        )
        Question.objects.create(
            assignment=a, order=0, question_type='mcq',
            question_text='Q?',
            options=[
                {'key': 'A', 'text': 'x'},
                {'key': 'B', 'text': 'y'},
            ],
            correct_answer='A', marks=1,
        )
        return a

    # --- Counts ------------------------------------------------------------

    def test_dashboard_shows_real_active_quest_count(self):
        u = self._student()
        a1 = self._assignment('QuestOne')
        a2 = self._assignment('QuestTwo', due_in_hours=72)
        StudentAssignment.objects.create(
            student=u, assignment=a1,
            status=StudentAssignment.STATUS_PENDING,
        )
        StudentAssignment.objects.create(
            student=u, assignment=a2,
            status=StudentAssignment.STATUS_IN_PROGRESS,
        )
        self.client.force_login(u)
        resp = self.client.get(reverse('web:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['active_quest_count'], 2)

    def test_dashboard_renders_overdue_chip(self):
        u = self._student()
        a = self._assignment('OverdueOne', due_in_hours=-24)
        StudentAssignment.objects.create(
            student=u, assignment=a,
            status=StudentAssignment.STATUS_PENDING,
        )
        self.client.force_login(u)
        resp = self.client.get(reverse('web:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'OVERDUE')
        self.assertEqual(resp.context['overdue_quest_count'], 1)

    # --- Rendering ---------------------------------------------------------

    def test_dashboard_renders_quest_titles(self):
        u = self._student()
        titles = ['AlphaQuest', 'BetaQuest', 'GammaQuest']
        for i, t in enumerate(titles):
            a = self._assignment(t, due_in_hours=48 + i)
            StudentAssignment.objects.create(
                student=u, assignment=a,
                status=StudentAssignment.STATUS_PENDING,
            )
        self.client.force_login(u)
        resp = self.client.get(reverse('web:dashboard'))
        self.assertEqual(resp.status_code, 200)
        for t in titles:
            self.assertContains(resp, t)

    def test_dashboard_renders_active_hunts(self):
        u = self._student()
        g1 = Goal.objects.create(
            student=u, title='HuntA', subject=self.subject,
            target_date=timezone.localdate() + timedelta(days=14),
            progress_pct=30, xp_reward=150, status=Goal.STATUS_ACTIVE,
        )
        g2 = Goal.objects.create(
            student=u, title='HuntB',
            target_date=timezone.localdate() + timedelta(days=7),
            progress_pct=60, xp_reward=200, status=Goal.STATUS_ACTIVE,
        )
        self.client.force_login(u)
        resp = self.client.get(reverse('web:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'HuntA')
        self.assertContains(resp, 'HuntB')
        # Progress bars — violet
        self.assertContains(resp, 'sys-progress sys-progress--violet')
        # Progress percentages in inline style
        self.assertContains(resp, 'width: 30%')
        self.assertContains(resp, 'width: 60%')
        # Active hunt rows in context
        ids = [g.id for g in resp.context['active_hunt_rows']]
        self.assertIn(g1.id, ids)
        self.assertIn(g2.id, ids)

    def test_dashboard_empty_state_when_no_quests(self):
        u = self._student('empty@t.test')
        self.client.force_login(u)
        resp = self.client.get(reverse('web:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['active_quest_count'], 0)
        self.assertEqual(list(resp.context['active_quest_rows']), [])
        self.assertEqual(list(resp.context['active_hunt_rows']), [])
        # "+ Begin Hunt" ghost button points at hunt_new
        self.assertContains(resp, reverse('student:hunt_new'))
        # Empty state text for no quests
        self.assertContains(resp, 'No active quests yet')

    # --- Streak engine integration ----------------------------------------

    def test_dashboard_calls_recompute_streak(self):
        u = self._student('streak-hook@t.test')
        self.client.force_login(u)
        with patch(
            'apps.service.services.streaks.recompute_streak',
            return_value={
                'ran': True, 'streak_days': 0,
                'shields': 1, 'milestones_fired': [],
            },
        ) as mock_recompute:
            resp = self.client.get(reverse('web:dashboard'))
        self.assertEqual(resp.status_code, 200)
        mock_recompute.assert_called_once()
        # It's called with a StudentProfile instance.
        (profile_arg,), _kwargs = mock_recompute.call_args
        self.assertEqual(profile_arg.student_id, u.id)
