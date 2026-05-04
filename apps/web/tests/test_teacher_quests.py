"""Tests for the teacher-facing Quest management UI."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, Tenant, User
from apps.service.models import Assignment, Class, ClassSubject, Subject


def _ensure_roles():
    Role.objects.get_or_create(
        name=Role.TEACHER, defaults={'display_name': 'Teacher', 'level': 50})
    Role.objects.get_or_create(
        name=Role.STUDENT, defaults={'display_name': 'Student', 'level': 100})


class TeacherQuestCreateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _ensure_roles()
        cls.tenant = Tenant.objects.create(name='TQ School', slug='tq')
        cls.teacher_role = Role.objects.get(name=Role.TEACHER)
        cls.subject = Subject.objects.create(
            tenant=cls.tenant, code='SCI', name='Science')

    def _teacher(self, email='t@tq.test'):
        return User.objects.create_user(
            email=email, password='p', first_name='T', last_name='X',
            tenant=self.tenant, role=self.teacher_role,
            is_active=True, employee_id='E1',
        )

    def _class_for(self, teacher):
        cls = Class.objects.create(
            tenant=self.tenant, name='G8A', grade_level=8, section='A',
            academic_year='2025-2026', class_teacher=teacher,
        )
        ClassSubject.objects.create(class_obj=cls, subject=self.subject, teacher=teacher)
        return cls

    def test_list_requires_login(self):
        resp = self.client.get(reverse('teacher:quest_list'))
        self.assertEqual(resp.status_code, 302)

    def test_create_form_renders(self):
        t = self._teacher()
        self._class_for(t)
        self.client.force_login(t)
        resp = self.client.get(reverse('teacher:quest_create'))
        self.assertEqual(resp.status_code, 200)

    def test_create_submits_and_generates_draft_questions(self):
        t = self._teacher()
        cls = self._class_for(t)
        self.client.force_login(t)
        due = (timezone.now() + timedelta(days=5)).strftime('%Y-%m-%dT%H:%M')
        with patch(
            'apps.web.views.teacher.quests.QuestionGenerator',
        ) as MockGen:
            MockGen.return_value.generate_questions.return_value = [
                {
                    'question': 'What is photosynthesis?',
                    'options': [
                        'A) A chemical reaction',
                        'B) A car brand',
                        'C) A sport',
                        'D) A song',
                    ],
                    'correct_answer': 'A) A chemical reaction',
                    'explanation': 'It is the process plants use.',
                    'type': 'mcq',
                },
            ]
            resp = self.client.post(reverse('teacher:quest_create'), {
                'title': 'Photosynthesis Quiz',
                'description': 'Quick test',
                'class_obj': cls.id,
                'subject': self.subject.id,
                'topic': '',
                'count': '1',
                'difficulty': '3',
                'due_date': due,
            })
        self.assertEqual(resp.status_code, 302)
        a = Assignment.objects.get(tenant=self.tenant, title='Photosynthesis Quiz')
        self.assertEqual(a.status, Assignment.STATUS_DRAFT)
        self.assertEqual(a.questions.count(), 1)
        q = a.questions.first()
        # The normalize_options step should produce structured options
        self.assertEqual(len(q.options), 4)
        self.assertEqual(q.correct_answer, 'A')

    def test_publish_flips_status(self):
        t = self._teacher()
        cls = self._class_for(t)
        a = Assignment.objects.create(
            tenant=self.tenant, class_obj=cls, subject=self.subject,
            title='Pub Quest', description='',
            due_date=timezone.now() + timedelta(days=3),
            total_marks=1, difficulty=3, reward_xp=15,
            status=Assignment.STATUS_DRAFT, created_by=t, updated_by=t,
        )
        # Need at least one question to publish
        from apps.service.models import Question
        Question.objects.create(
            assignment=a, order=0, question_type='mcq',
            question_text='x?', options=[{'key': 'A', 'text': 'yes'}],
            correct_answer='A', marks=1,
        )
        self.client.force_login(t)
        resp = self.client.post(reverse('teacher:quest_publish', args=[a.id]))
        self.assertEqual(resp.status_code, 302)
        a.refresh_from_db()
        self.assertEqual(a.status, Assignment.STATUS_PUBLISHED)
        self.assertIsNotNone(a.published_at)

    def test_publish_blocks_empty_assignment(self):
        t = self._teacher()
        cls = self._class_for(t)
        a = Assignment.objects.create(
            tenant=self.tenant, class_obj=cls, subject=self.subject,
            title='Empty Quest',
            due_date=timezone.now() + timedelta(days=3),
            total_marks=0, difficulty=2, reward_xp=0,
            status=Assignment.STATUS_DRAFT, created_by=t, updated_by=t,
        )
        self.client.force_login(t)
        resp = self.client.post(reverse('teacher:quest_publish', args=[a.id]))
        a.refresh_from_db()
        self.assertEqual(a.status, Assignment.STATUS_DRAFT)

    def test_cannot_access_other_teachers_quest(self):
        t = self._teacher('me@tq.test')
        other = User.objects.create_user(
            email='other@tq.test', password='p', first_name='O', last_name='X',
            tenant=self.tenant, role=self.teacher_role, is_active=True,
        )
        other_cls = Class.objects.create(
            tenant=self.tenant, name='G9B', grade_level=9, section='B',
            academic_year='2025-2026', class_teacher=other,
        )
        ClassSubject.objects.create(class_obj=other_cls, subject=self.subject, teacher=other)
        a = Assignment.objects.create(
            tenant=self.tenant, class_obj=other_cls, subject=self.subject,
            title='Not Yours',
            due_date=timezone.now() + timedelta(days=3),
            total_marks=1, difficulty=1, reward_xp=5,
            status=Assignment.STATUS_DRAFT, created_by=other, updated_by=other,
        )
        self.client.force_login(t)
        resp = self.client.get(reverse('teacher:quest_detail', args=[a.id]))
        self.assertEqual(resp.status_code, 404)
