"""Tests for the mastery moving-average service + wire-in at grading / hunt quiz."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, Tenant, User
from apps.service.models import (
    Assignment,
    Class,
    Goal,
    Question,
    StudentProfile,
    Subject,
    Task,
)
from apps.service.services.mastery import apply_mastery_update
from apps.service.services.quests import (
    grade_student_assignment,
    save_draft_answers,
    start_attempt,
)


def _ensure_roles():
    Role.objects.get_or_create(
        name=Role.STUDENT, defaults={'display_name': 'Student', 'level': 100},
    )


class MasteryWeightedMATests(TestCase):
    """Pure unit tests for `apply_mastery_update`'s 0.7/0.3 formula."""

    @classmethod
    def setUpTestData(cls):
        _ensure_roles()
        cls.tenant = Tenant.objects.create(name='M School', slug='msch')
        cls.student_role = Role.objects.get(name=Role.STUDENT)
        cls.subject = Subject.objects.create(
            tenant=cls.tenant, code='SCI', name='Science',
        )

    def _profile(self, email='m@t.test', initial_mastery=None):
        u = User.objects.create_user(
            email=email, password='p', first_name='M', last_name='S',
            tenant=self.tenant, role=self.student_role,
            is_active=True, grade_level=8,
        )
        p, _ = StudentProfile.objects.get_or_create(student=u)
        if initial_mastery is not None:
            p.mastery_per_subject = dict(initial_mastery)
            p.save(update_fields=['mastery_per_subject', 'updated_at'])
        return p

    def test_prior_50_new_100_gives_65(self):
        p = self._profile('a@t.test', {str(self.subject.id): 50})
        updated = apply_mastery_update(p, self.subject.id, 100)
        self.assertEqual(updated, 65)  # round(0.7*50 + 0.3*100)
        p.refresh_from_db()
        self.assertEqual(p.mastery_per_subject[str(self.subject.id)], 65)

    def test_prior_50_new_0_gives_35(self):
        p = self._profile('b@t.test', {str(self.subject.id): 50})
        updated = apply_mastery_update(p, self.subject.id, 0)
        self.assertEqual(updated, 35)  # round(0.7*50 + 0.3*0)
        p.refresh_from_db()
        self.assertEqual(p.mastery_per_subject[str(self.subject.id)], 35)

    def test_no_prior_defaults_to_50(self):
        # Empty mastery dict -> default prior 50
        p = self._profile('c@t.test', {})
        updated = apply_mastery_update(p, self.subject.id, 80)
        self.assertEqual(updated, 59)  # round(0.7*50 + 0.3*80) = round(59) = 59
        p.refresh_from_db()
        self.assertEqual(p.mastery_per_subject[str(self.subject.id)], 59)

    def test_subject_id_none_is_noop(self):
        p = self._profile('d@t.test', {str(self.subject.id): 42})
        result = apply_mastery_update(p, None, 90)
        self.assertIsNone(result)
        p.refresh_from_db()
        # Unchanged
        self.assertEqual(p.mastery_per_subject, {str(self.subject.id): 42})

    def test_profile_none_is_noop(self):
        result = apply_mastery_update(None, self.subject.id, 90)
        self.assertIsNone(result)

    def test_score_clamps_to_0_and_100(self):
        # Negative treated as 0; prior 50 -> round(0.7*50 + 0.3*0) = 35
        p_low = self._profile('lo@t.test', {str(self.subject.id): 50})
        low = apply_mastery_update(p_low, self.subject.id, -15)
        self.assertEqual(low, 35)

        # 150 treated as 100; prior 50 -> round(0.7*50 + 0.3*100) = 65
        p_high = self._profile('hi@t.test', {str(self.subject.id): 50})
        high = apply_mastery_update(p_high, self.subject.id, 150)
        self.assertEqual(high, 65)


class QuestGradingMasteryIntegrationTests(TestCase):
    """grade_student_assignment should nudge mastery for the subject."""

    @classmethod
    def setUpTestData(cls):
        _ensure_roles()
        cls.tenant = Tenant.objects.create(name='QG School', slug='qgsch')
        cls.student_role = Role.objects.get(name=Role.STUDENT)
        cls.subject = Subject.objects.create(
            tenant=cls.tenant, code='MATH', name='Mathematics',
        )
        cls.cls_obj = Class.objects.create(
            tenant=cls.tenant, name='G8-A',
            grade_level=8, section='A', academic_year='2025-2026',
        )

    def _student(self, email='qg@t.test'):
        u = User.objects.create_user(
            email=email, password='p', first_name='Q', last_name='G',
            tenant=self.tenant, role=self.student_role,
            is_active=True, grade_level=8,
        )
        StudentProfile.objects.get_or_create(student=u)
        return u

    def test_quest_grading_updates_mastery(self):
        u = self._student()
        # Seed a known prior: 50
        u.profile.mastery_per_subject = {str(self.subject.id): 50}
        u.profile.save(update_fields=['mastery_per_subject', 'updated_at'])

        a = Assignment.objects.create(
            tenant=self.tenant, class_obj=self.cls_obj, subject=self.subject,
            title='Mastery Quest', description='',
            due_date=timezone.now() + timedelta(hours=48),
            total_marks=1, difficulty=3, reward_xp=50,
            status=Assignment.STATUS_PUBLISHED,
        )
        q = Question.objects.create(
            assignment=a, order=0, question_type=Question.TYPE_MCQ,
            question_text='Pick A',
            options=[{'key': 'A', 'text': 'A'}, {'key': 'B', 'text': 'B'}],
            correct_answer='A', marks=1,
        )
        sa = start_attempt(u, a)
        save_draft_answers(sa, [
            {'question_id': q.id, 'selected_option_key': 'A'},
        ])
        grade_student_assignment(sa)

        u.profile.refresh_from_db()
        # 100% correct — prior 50 -> round(0.7*50 + 0.3*100) = 65
        self.assertEqual(
            u.profile.mastery_per_subject[str(self.subject.id)], 65,
        )


class HuntQuizMasteryIntegrationTests(TestCase):
    """Passing a hunt-task quiz should nudge mastery for the goal's subject."""

    @classmethod
    def setUpTestData(cls):
        _ensure_roles()
        cls.tenant = Tenant.objects.create(name='HM School', slug='hmsch')
        cls.student_role = Role.objects.get(name=Role.STUDENT)
        cls.subject = Subject.objects.create(
            tenant=cls.tenant, code='ENG', name='English',
        )

    def _student(self, email='hm@t.test'):
        u = User.objects.create_user(
            email=email, password='p', first_name='H', last_name='M',
            tenant=self.tenant, role=self.student_role,
            is_active=True, grade_level=8,
        )
        StudentProfile.objects.create(student=u, onboarding_complete=True)
        return u

    def _canned_quiz(self, count=3):
        return [
            {
                'question': f'Q{i + 1}?',
                'options': [
                    {'key': 'A', 'text': 'Right'},
                    {'key': 'B', 'text': 'Wrong'},
                    {'key': 'C', 'text': 'Wrong'},
                    {'key': 'D', 'text': 'Wrong'},
                ],
                'correct_answer': 'A',
                'explanation': '',
            }
            for i in range(count)
        ]

    def test_hunt_quiz_passing_updates_mastery(self):
        u = self._student()
        # Seed a known prior: 50
        u.profile.mastery_per_subject = {str(self.subject.id): 50}
        u.profile.save(update_fields=['mastery_per_subject', 'updated_at'])

        g = Goal.objects.create(
            student=u, title='Mastery Hunt', subject=self.subject,
            target_date=timezone.localdate() + timedelta(days=10),
        )
        t = Task.objects.create(
            goal=g, order=0, title='Solo', kind='practice', xp_reward=25,
            quiz_questions=self._canned_quiz(5),
        )

        self.client.force_login(u)
        resp = self.client.post(
            reverse('student:hunt_task_quiz', args=[t.id]),
            data={f'q_{i}': 'A' for i in range(5)},  # 100% correct
        )
        self.assertEqual(resp.status_code, 200)

        u.profile.refresh_from_db()
        # 100% — prior 50 -> round(0.7*50 + 0.3*100) = 65
        self.assertEqual(
            u.profile.mastery_per_subject[str(self.subject.id)], 65,
        )
