"""Tests for the hunt task quiz service (`apps.service.services.hunts.quiz`)."""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import Role, Tenant, User
from apps.service.models import ContentNode, Document, Goal, Subject, Task
from apps.service.services.hunts import quiz as quiz_service


def _roles():
    Role.objects.get_or_create(
        name=Role.STUDENT, defaults={'display_name': 'Student', 'level': 100})


class EnsureQuizQuestionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _roles()
        cls.tenant = Tenant.objects.create(name='Q', slug='q')
        cls.student_role = Role.objects.get(name=Role.STUDENT)
        cls.subject = Subject.objects.create(tenant=cls.tenant, code='SCI', name='Science')
        cls.doc = Document.objects.create(
            tenant=cls.tenant, title='Book', source_type='synthetic')
        cls.node = ContentNode.objects.create(
            tenant=cls.tenant, subject=cls.subject, document=cls.doc,
            node_id='ch1.s1', node_type='topic', title='Photosynthesis',
            content='Photosynthesis converts light energy into chemical energy.',
            content_plain='Photosynthesis converts light energy into chemical energy.',
        )

    def _student_goal_task(self, kind='read', ref_node=None):
        u = User.objects.create_user(
            email=f'{kind}@q.test', password='p', first_name='S', last_name='T',
            tenant=self.tenant, role=self.student_role, is_active=True,
            grade_level=8,
        )
        g = Goal.objects.create(
            student=u, title='G', subject=self.subject,
            target_date=timezone.localdate() + timedelta(days=10),
        )
        t = Task.objects.create(
            goal=g, order=0, title='T', kind=kind, xp_reward=10,
            ref_node=ref_node,
        )
        return t

    @override_settings(OPENAI_API_KEY='')
    def test_stub_fallback_when_no_api_key(self):
        t = self._student_goal_task()
        questions = quiz_service.ensure_quiz_questions(t)
        self.assertEqual(len(questions), t.required_questions())
        for q in questions:
            self.assertIn('options', q)
            self.assertEqual(len(q['options']), 4)
            self.assertEqual(q['correct_answer'], 'A')
            self.assertTrue(q['options'][0]['text'])

    @override_settings(OPENAI_API_KEY='')
    def test_cached_on_second_call(self):
        t = self._student_goal_task()
        q1 = quiz_service.ensure_quiz_questions(t)
        t.refresh_from_db()
        q2 = quiz_service.ensure_quiz_questions(t)
        self.assertEqual(q1, q2)

    @override_settings(OPENAI_API_KEY='')
    def test_boss_kind_asks_10_questions(self):
        t = self._student_goal_task(kind='boss')
        questions = quiz_service.ensure_quiz_questions(t)
        self.assertEqual(len(questions), 10)

    @override_settings(OPENAI_API_KEY='sk-test')
    @patch('apps.service.services.hunts.quiz.QuestionGenerator')
    def test_llm_called_with_content_grounding(self, mock_gen_cls):
        mock_instance = mock_gen_cls.return_value
        mock_instance.generate_questions.return_value = [
            {
                'question': 'What does photosynthesis convert?',
                'options': ['A) Light energy', 'B) Sound', 'C) Matter', 'D) None'],
                'correct_answer': 'A) Light energy',
                'explanation': 'Per the passage.',
            },
            {
                'question': 'Source of energy?',
                'options': ['A) Sunlight', 'B) Heat', 'C) Water', 'D) Air'],
                'correct_answer': 'A',
                'explanation': 'Passage says so.',
            },
            {
                'question': 'Output?',
                'options': ['A) Chemical energy', 'B) Electric', 'C) Nuclear', 'D) Thermal'],
                'correct_answer': 'A',
                'explanation': 'Direct citation.',
            },
        ]
        t = self._student_goal_task(kind='read', ref_node=self.node)
        quiz_service.ensure_quiz_questions(t)
        # Verify the LLM was called with curriculum content grounding
        _, kwargs = mock_instance.generate_questions.call_args
        self.assertEqual(kwargs['topic'], 'Photosynthesis')
        self.assertIn('Photosynthesis converts light energy', kwargs['content_context'])
        self.assertEqual(kwargs['subject_context'], 'Science')
        self.assertEqual(kwargs['grade_level'], 8)


class GradeQuizTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _roles()
        cls.tenant = Tenant.objects.create(name='Q2', slug='q2')
        cls.student_role = Role.objects.get(name=Role.STUDENT)

    def _task(self, kind='read', questions=None):
        u = User.objects.create_user(
            email=f'{kind}@q2.test', password='p', first_name='S', last_name='T',
            tenant=self.tenant, role=self.student_role, is_active=True,
            grade_level=8,
        )
        g = Goal.objects.create(
            student=u, title='G',
            target_date=timezone.localdate() + timedelta(days=10),
        )
        return Task.objects.create(
            goal=g, order=0, title='T', kind=kind, xp_reward=10,
            quiz_questions=questions or [
                {'question': 'Q1', 'options': [
                    {'key': 'A', 'text': 'x'}, {'key': 'B', 'text': 'y'},
                    {'key': 'C', 'text': 'z'}, {'key': 'D', 'text': 'w'},
                ], 'correct_answer': 'A', 'explanation': ''},
                {'question': 'Q2', 'options': [
                    {'key': 'A', 'text': 'x'}, {'key': 'B', 'text': 'y'},
                    {'key': 'C', 'text': 'z'}, {'key': 'D', 'text': 'w'},
                ], 'correct_answer': 'B', 'explanation': ''},
                {'question': 'Q3', 'options': [
                    {'key': 'A', 'text': 'x'}, {'key': 'B', 'text': 'y'},
                    {'key': 'C', 'text': 'z'}, {'key': 'D', 'text': 'w'},
                ], 'correct_answer': 'C', 'explanation': ''},
            ],
        )

    def test_all_correct_passes(self):
        t = self._task()
        result = quiz_service.grade_quiz(t, [
            {'qid': 0, 'selected': 'A'},
            {'qid': 1, 'selected': 'B'},
            {'qid': 2, 'selected': 'C'},
        ])
        self.assertEqual(result['correct'], 3)
        self.assertEqual(result['total'], 3)
        self.assertEqual(result['pct'], 100)
        self.assertTrue(result['passed'])
        self.assertEqual(len(result['details']), 3)
        self.assertTrue(all(d['is_correct'] for d in result['details']))

    def test_below_threshold_fails(self):
        t = self._task(kind='read')  # threshold 67
        # 1/3 = 33% < 67%
        result = quiz_service.grade_quiz(t, [
            {'qid': 0, 'selected': 'A'},
            {'qid': 1, 'selected': 'A'},
            {'qid': 2, 'selected': 'A'},
        ])
        self.assertEqual(result['correct'], 1)
        self.assertEqual(result['pct'], 33)
        self.assertFalse(result['passed'])

    def test_exactly_at_threshold_passes(self):
        t = self._task(kind='read')  # threshold 67
        # 2/3 = 67% — meets threshold
        result = quiz_service.grade_quiz(t, [
            {'qid': 0, 'selected': 'A'},
            {'qid': 1, 'selected': 'B'},
            {'qid': 2, 'selected': 'A'},  # wrong
        ])
        self.assertEqual(result['pct'], 67)
        self.assertTrue(result['passed'])

    def test_boss_threshold_is_70_percent(self):
        t = self._task(kind='boss', questions=[
            {'question': f'Q{i}', 'options': [
                {'key': 'A', 'text': 'x'}, {'key': 'B', 'text': 'y'},
                {'key': 'C', 'text': 'z'}, {'key': 'D', 'text': 'w'},
            ], 'correct_answer': 'A', 'explanation': ''} for i in range(10)
        ])
        # 7/10 = 70% → passes
        result = quiz_service.grade_quiz(t, [
            {'qid': i, 'selected': 'A' if i < 7 else 'B'} for i in range(10)
        ])
        self.assertTrue(result['passed'])
        # 6/10 = 60% → fails boss
        result = quiz_service.grade_quiz(t, [
            {'qid': i, 'selected': 'A' if i < 6 else 'B'} for i in range(10)
        ])
        self.assertFalse(result['passed'])

    def test_empty_responses_all_wrong(self):
        t = self._task()
        result = quiz_service.grade_quiz(t, [])
        self.assertEqual(result['correct'], 0)
        self.assertEqual(result['pct'], 0)
        self.assertFalse(result['passed'])
