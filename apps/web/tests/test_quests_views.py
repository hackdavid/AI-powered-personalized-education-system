"""Tests for student quest (Assignment) views."""

import json
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, Tenant, User
from apps.service.models import (
    Assignment, Class, Enrollment, Question, StudentAssignment, StudentProfile, Subject,
)


def _ensure_roles():
    Role.objects.get_or_create(
        name=Role.STUDENT, defaults={'display_name': 'Student', 'level': 100})
    Role.objects.get_or_create(
        name=Role.TEACHER, defaults={'display_name': 'Teacher', 'level': 50})


class QuestFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _ensure_roles()
        cls.tenant = Tenant.objects.create(name='Quest Test', slug='quest')
        cls.student_role = Role.objects.get(name=Role.STUDENT)
        cls.cls = Class.objects.create(
            tenant=cls.tenant, name='G8A', grade_level=8, section='A',
            academic_year='2025-2026',
        )
        cls.subject = Subject.objects.create(
            tenant=cls.tenant, code='MATH', name='Mathematics')

    def _student(self, email='s@quest.test'):
        u = User.objects.create_user(
            email=email, password='p', first_name='S', last_name='T',
            tenant=self.tenant, role=self.student_role,
            is_active=True, grade_level=8,
        )
        StudentProfile.objects.create(student=u, onboarding_complete=True)
        Enrollment.objects.create(class_obj=self.cls, student=u)
        return u

    def _assignment(self, title='TestQuest', due_hours=48):
        a = Assignment.objects.create(
            tenant=self.tenant, class_obj=self.cls, subject=self.subject,
            title=title, description='descriptive text',
            due_date=timezone.now() + timedelta(hours=due_hours),
            total_marks=2, difficulty=3, reward_xp=30,
            status=Assignment.STATUS_PUBLISHED, published_at=timezone.now(),
        )
        Question.objects.create(
            assignment=a, order=0, question_type='mcq',
            question_text='2+2?',
            options=[
                {'key': 'A', 'text': '3'},
                {'key': 'B', 'text': '4'},
                {'key': 'C', 'text': '5'},
                {'key': 'D', 'text': '22'},
            ],
            correct_answer='B', marks=1,
        )
        Question.objects.create(
            assignment=a, order=1, question_type='mcq',
            question_text='5-1?',
            options=[
                {'key': 'A', 'text': '4'},
                {'key': 'B', 'text': '6'},
            ],
            correct_answer='A', marks=1,
        )
        return a

    def test_list_requires_login(self):
        resp = self.client.get(reverse('student:quest_list'))
        self.assertEqual(resp.status_code, 302)

    def test_list_renders_published_for_enrolled_student(self):
        u = self._student()
        self._assignment('MathQuestA')
        self.client.force_login(u)
        resp = self.client.get(reverse('student:quest_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'MathQuestA')

    def test_list_does_not_show_draft_assignments(self):
        u = self._student()
        Assignment.objects.create(
            tenant=self.tenant, class_obj=self.cls, subject=self.subject,
            title='DraftQuest', due_date=timezone.now() + timedelta(hours=24),
            total_marks=5, difficulty=2, reward_xp=10,
            status=Assignment.STATUS_DRAFT,
        )
        self.client.force_login(u)
        resp = self.client.get(reverse('student:quest_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, 'DraftQuest')

    def test_chamber_creates_attempt_and_renders(self):
        u = self._student()
        a = self._assignment()
        self.client.force_login(u)
        resp = self.client.get(reverse('student:quest_chamber', args=[a.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            StudentAssignment.objects.filter(student=u, assignment=a).exists()
        )

    def test_save_draft_upserts_answers(self):
        u = self._student()
        a = self._assignment()
        self.client.force_login(u)
        self.client.get(reverse('student:quest_chamber', args=[a.id]))
        qs = list(a.questions.all())
        resp = self.client.post(
            reverse('student:quest_save_draft', args=[a.id]),
            data=json.dumps({'answers': [
                {'question_id': qs[0].id, 'selected_option_key': 'A'},
            ]}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        sa = StudentAssignment.objects.get(student=u, assignment=a)
        answer = sa.answers.get(question=qs[0])
        self.assertEqual(answer.selected_option_key, 'A')

    def test_submit_full_correct_awards_xp(self):
        u = self._student()
        a = self._assignment()
        self.client.force_login(u)
        self.client.get(reverse('student:quest_chamber', args=[a.id]))
        qs = list(a.questions.all())
        resp = self.client.post(
            reverse('student:quest_submit', args=[a.id]),
            data=json.dumps({'answers': [
                {'question_id': qs[0].id, 'selected_option_key': 'B'},
                {'question_id': qs[1].id, 'selected_option_key': 'A'},
            ]}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        sa = StudentAssignment.objects.get(student=u, assignment=a)
        self.assertEqual(sa.status, 'graded')
        self.assertEqual(sa.score, 2)
        self.assertGreater(sa.xp_awarded, 0)

    def test_submit_partial_credit_scales_xp(self):
        u = self._student()
        a = self._assignment()
        self.client.force_login(u)
        self.client.get(reverse('student:quest_chamber', args=[a.id]))
        qs = list(a.questions.all())
        self.client.post(
            reverse('student:quest_submit', args=[a.id]),
            data=json.dumps({'answers': [
                {'question_id': qs[0].id, 'selected_option_key': 'B'},
                {'question_id': qs[1].id, 'selected_option_key': 'B'},
            ]}),
            content_type='application/json',
        )
        sa = StudentAssignment.objects.get(student=u, assignment=a)
        self.assertEqual(sa.status, 'graded')
        self.assertEqual(sa.score, 1)
        self.assertLess(sa.xp_awarded, 30)

    def test_results_view_after_grading_renders(self):
        u = self._student()
        a = self._assignment()
        sa = StudentAssignment.objects.create(
            student=u, assignment=a, max_score=2, score=1,
            status='graded', graded_at=timezone.now(),
            xp_awarded=15,
        )
        self.client.force_login(u)
        resp = self.client.get(reverse('student:quest_results', args=[a.id]))
        self.assertEqual(resp.status_code, 200)

    def test_cannot_access_unenrolled_quest(self):
        outsider = User.objects.create_user(
            email='out@quest.test', password='p',
            first_name='Out', last_name='X',
            tenant=self.tenant, role=self.student_role,
            is_active=True, grade_level=8,
        )
        StudentProfile.objects.create(student=outsider, onboarding_complete=True)
        # Also create a different class so grade-level fallback doesn't match
        other_cls = Class.objects.create(
            tenant=self.tenant, name='G9A', grade_level=9, section='A',
            academic_year='2025-2026',
        )
        outsider.grade_level = 9
        outsider.save(update_fields=['grade_level'])
        a = self._assignment()
        self.client.force_login(outsider)
        resp = self.client.get(reverse('student:quest_chamber', args=[a.id]))
        self.assertEqual(resp.status_code, 404)

    def test_submitted_quest_redirects_to_results_on_chamber(self):
        u = self._student()
        a = self._assignment()
        StudentAssignment.objects.create(
            student=u, assignment=a, status='graded',
            score=2, max_score=2, graded_at=timezone.now(),
        )
        self.client.force_login(u)
        resp = self.client.get(
            reverse('student:quest_chamber', args=[a.id]), follow=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('student:quest_results', args=[a.id]), resp.url)
