"""Phase F: Tests for teacher grading interface.

Tests that teachers can:
- View student submissions with answers
- Grade submissions (assign marks per question + feedback)
- Update StudentAssignment status to GRADED
- Access control: only grade their own students' submissions
"""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, Tenant, User
from apps.service.models import (
    Answer,
    Assignment,
    Class,
    ClassSubject,
    Enrollment,
    Question,
    StudentAssignment,
    Subject,
)


def _ensure_roles():
    Role.objects.get_or_create(
        name=Role.TEACHER, defaults={'display_name': 'Teacher', 'level': 50})
    Role.objects.get_or_create(
        name=Role.STUDENT, defaults={'display_name': 'Student', 'level': 100})


class GradingFixtureMixin:
    """Shared setup: teacher, class, student, assignment, submission."""

    @classmethod
    def setUpTestData(cls):
        _ensure_roles()
        cls.tenant = Tenant.objects.create(name='Grading School', slug='grs')
        cls.other_tenant = Tenant.objects.create(name='Other School', slug='ots')
        cls.teacher_role = Role.objects.get(name=Role.TEACHER)
        cls.student_role = Role.objects.get(name=Role.STUDENT)

        # My teacher + class
        cls.teacher = cls._mk_teacher('teacher@grs.test')
        cls.subject = Subject.objects.create(
            tenant=cls.tenant, code='MATH', name='Math')
        cls.my_class = cls._mk_class(cls.teacher, 'Math 8A')

        # Student + enrollment
        cls.alice = cls._mk_student('alice@grs.test', first='Alice', last='A')
        Enrollment.objects.create(
            class_obj=cls.my_class, student=cls.alice, is_active=True)

        # Published assignment with MCQ + short answer
        now = timezone.now()
        cls.assignment = Assignment.objects.create(
            tenant=cls.tenant, class_obj=cls.my_class, subject=cls.subject,
            title='Quiz 1', due_date=now + timedelta(days=7),
            status=Assignment.STATUS_PUBLISHED, total_marks=15,
            created_by=cls.teacher, updated_by=cls.teacher,
        )
        cls.q1_mcq = Question.objects.create(
            assignment=cls.assignment, order=0, question_type=Question.TYPE_MCQ,
            question_text='What is 2+2?',
            options=[{'key': 'A', 'text': '3'}, {'key': 'B', 'text': '4'}],
            correct_answer='B', marks=5,
        )
        cls.q2_short = Question.objects.create(
            assignment=cls.assignment, order=1, question_type=Question.TYPE_SHORT,
            question_text='Explain photosynthesis.',
            correct_answer='Plants convert light to energy.', marks=10,
        )

        # Student submission (SUBMITTED status, not yet graded)
        cls.submission = StudentAssignment.objects.create(
            assignment=cls.assignment, student=cls.alice,
            status=StudentAssignment.STATUS_SUBMITTED,
            submitted_at=now, max_score=15,
        )
        # Alice answered correctly for MCQ, partial for short
        cls.ans1 = Answer.objects.create(
            student_assignment=cls.submission, question=cls.q1_mcq,
            selected_option_key='B',
        )
        cls.ans2 = Answer.objects.create(
            student_assignment=cls.submission, question=cls.q2_short,
            answer_text='Plants use sunlight.',
        )

        # Other teacher (same tenant)
        cls.other_teacher = cls._mk_teacher('other@grs.test')
        cls.other_class = cls._mk_class(cls.other_teacher, 'Science 9B')
        cls.bob = cls._mk_student('bob@grs.test', first='Bob', last='B')
        Enrollment.objects.create(
            class_obj=cls.other_class, student=cls.bob, is_active=True)

    @classmethod
    def _mk_teacher(cls, email, tenant=None):
        return User.objects.create_user(
            email=email, password='p', first_name='T', last_name='X',
            tenant=tenant or cls.tenant, role=cls.teacher_role,
            is_active=True, employee_id=f'E{User.objects.count()}',
        )

    @classmethod
    def _mk_student(cls, email, first='S', last='X', tenant=None):
        return User.objects.create_user(
            email=email, password='p', first_name=first, last_name=last,
            tenant=tenant or cls.tenant, role=cls.student_role,
            is_active=True, student_id=f'S{User.objects.count()}',
        )

    @classmethod
    def _mk_class(cls, teacher, name, tenant=None):
        # Use different sections to avoid unique constraint
        section = chr(65 + Class.objects.count() % 26)  # A, B, C, etc.
        c = Class.objects.create(
            tenant=tenant or cls.tenant, name=name,
            grade_level=8 + (Class.objects.count() % 5), section=section,
            academic_year='2025-2026',
            class_teacher=teacher,
        )
        ClassSubject.objects.create(
            class_obj=c, subject=cls.subject, teacher=teacher)
        return c


# ---------------------------------------------------------------------------
# Grading View GET (display form)
# ---------------------------------------------------------------------------


class GradingViewGetTests(GradingFixtureMixin, TestCase):
    def test_anonymous_redirects_to_login(self):
        resp = self.client.get(reverse('teacher:grading_view', args=[self.submission.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp.url)

    def test_teacher_sees_grading_form(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse('teacher:grading_view', args=[self.submission.id]))
        self.assertEqual(resp.status_code, 200)
        # Should see student name, assignment title
        self.assertContains(resp, 'Alice A')
        self.assertContains(resp, 'Quiz 1')
        # Should see questions
        self.assertContains(resp, 'What is 2+2?')
        self.assertContains(resp, 'Explain photosynthesis')
        # Should see student's answers
        self.assertContains(resp, 'B: 4')  # MCQ answer
        self.assertContains(resp, 'Plants use sunlight')  # short answer

    def test_other_teachers_submission_returns_404(self):
        # Other teacher should not be able to view/grade my student's submission
        self.client.force_login(self.other_teacher)
        resp = self.client.get(reverse('teacher:grading_view', args=[self.submission.id]))
        self.assertEqual(resp.status_code, 404)

    def test_cross_tenant_submission_returns_404(self):
        # Cross-tenant teacher
        cross_teacher = self._mk_teacher('cross@ots.test', tenant=self.other_tenant)
        self.client.force_login(cross_teacher)
        resp = self.client.get(reverse('teacher:grading_view', args=[self.submission.id]))
        self.assertEqual(resp.status_code, 404)

    def test_shows_correct_answer_for_mcq(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse('teacher:grading_view', args=[self.submission.id]))
        # Should indicate that B is correct
        self.assertContains(resp, 'Correct')

    def test_shows_model_answer_for_short(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse('teacher:grading_view', args=[self.submission.id]))
        # Model answer should be displayed
        self.assertContains(resp, 'Plants convert light to energy')


# ---------------------------------------------------------------------------
# Grading View POST (save grades)
# ---------------------------------------------------------------------------


class GradingViewPostTests(GradingFixtureMixin, TestCase):
    def test_save_full_marks(self):
        self.client.force_login(self.teacher)
        data = {
            f'marks_{self.q1_mcq.id}': '5',
            f'feedback_{self.q1_mcq.id}': 'Perfect!',
            f'marks_{self.q2_short.id}': '10',
            f'feedback_{self.q2_short.id}': 'Excellent explanation.',
        }
        resp = self.client.post(
            reverse('teacher:grading_view', args=[self.submission.id]),
            data,
        )
        # Should redirect to gradebook
        self.assertEqual(resp.status_code, 302)
        self.assertIn('gradebook', resp.url)

        # Check StudentAssignment updated
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, StudentAssignment.STATUS_GRADED)
        self.assertEqual(self.submission.score, 15)
        self.assertEqual(self.submission.max_score, 15)
        self.assertIsNotNone(self.submission.graded_at)

        # Check Answer records updated
        self.ans1.refresh_from_db()
        self.assertEqual(self.ans1.marks_awarded, 5)
        self.assertEqual(self.ans1.feedback, 'Perfect!')
        self.assertTrue(self.ans1.is_correct)

        self.ans2.refresh_from_db()
        self.assertEqual(self.ans2.marks_awarded, 10)
        self.assertEqual(self.ans2.feedback, 'Excellent explanation.')
        self.assertTrue(self.ans2.is_correct)

    def test_save_partial_marks(self):
        self.client.force_login(self.teacher)
        data = {
            f'marks_{self.q1_mcq.id}': '5',  # full
            f'marks_{self.q2_short.id}': '6',  # partial (out of 10)
            f'feedback_{self.q2_short.id}': 'Good, but needs more detail.',
        }
        resp = self.client.post(
            reverse('teacher:grading_view', args=[self.submission.id]),
            data,
        )
        self.assertEqual(resp.status_code, 302)

        self.submission.refresh_from_db()
        self.assertEqual(self.submission.score, 11)  # 5 + 6
        self.assertEqual(self.submission.status, StudentAssignment.STATUS_GRADED)

        self.ans2.refresh_from_db()
        self.assertEqual(self.ans2.marks_awarded, 6)
        self.assertFalse(self.ans2.is_correct)  # not full marks

    def test_marks_exceed_max_shows_error(self):
        self.client.force_login(self.teacher)
        data = {
            f'marks_{self.q1_mcq.id}': '10',  # exceeds 5
            f'marks_{self.q2_short.id}': '10',
        }
        resp = self.client.post(
            reverse('teacher:grading_view', args=[self.submission.id]),
            data,
        )
        # Should stay on same page with error
        self.assertEqual(resp.status_code, 302)  # redirect back to grading
        self.submission.refresh_from_db()
        # Should NOT be graded yet (error occurred)
        self.assertEqual(self.submission.status, StudentAssignment.STATUS_SUBMITTED)

    def test_negative_marks_shows_error(self):
        self.client.force_login(self.teacher)
        data = {
            f'marks_{self.q1_mcq.id}': '-1',
            f'marks_{self.q2_short.id}': '10',
        }
        resp = self.client.post(
            reverse('teacher:grading_view', args=[self.submission.id]),
            data,
        )
        self.assertEqual(resp.status_code, 302)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, StudentAssignment.STATUS_SUBMITTED)

    def test_invalid_marks_shows_error(self):
        self.client.force_login(self.teacher)
        data = {
            f'marks_{self.q1_mcq.id}': 'abc',
            f'marks_{self.q2_short.id}': '10',
        }
        resp = self.client.post(
            reverse('teacher:grading_view', args=[self.submission.id]),
            data,
        )
        self.assertEqual(resp.status_code, 302)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, StudentAssignment.STATUS_SUBMITTED)

    def test_empty_marks_allowed_for_optional_questions(self):
        # Teacher can leave marks blank (not yet graded for that question)
        self.client.force_login(self.teacher)
        data = {
            f'marks_{self.q1_mcq.id}': '5',
            f'marks_{self.q2_short.id}': '',  # blank
        }
        resp = self.client.post(
            reverse('teacher:grading_view', args=[self.submission.id]),
            data,
        )
        self.assertEqual(resp.status_code, 302)

        self.submission.refresh_from_db()
        # Total = 5 (only q1 counted)
        self.assertEqual(self.submission.score, 5)
        self.assertEqual(self.submission.status, StudentAssignment.STATUS_GRADED)

        self.ans2.refresh_from_db()
        self.assertIsNone(self.ans2.marks_awarded)

    def test_other_teacher_cannot_grade(self):
        self.client.force_login(self.other_teacher)
        data = {
            f'marks_{self.q1_mcq.id}': '5',
            f'marks_{self.q2_short.id}': '10',
        }
        resp = self.client.post(
            reverse('teacher:grading_view', args=[self.submission.id]),
            data,
        )
        self.assertEqual(resp.status_code, 404)

        # Submission should remain unchanged
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.status, StudentAssignment.STATUS_SUBMITTED)

    def test_re_grading_updates_existing_grades(self):
        # Grade once
        self.client.force_login(self.teacher)
        data = {
            f'marks_{self.q1_mcq.id}': '3',
            f'marks_{self.q2_short.id}': '7',
        }
        self.client.post(
            reverse('teacher:grading_view', args=[self.submission.id]),
            data,
        )
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.score, 10)

        # Re-grade with different scores
        data = {
            f'marks_{self.q1_mcq.id}': '5',
            f'marks_{self.q2_short.id}': '10',
            f'feedback_{self.q2_short.id}': 'Updated feedback.',
        }
        resp = self.client.post(
            reverse('teacher:grading_view', args=[self.submission.id]),
            data,
        )
        self.assertEqual(resp.status_code, 302)

        self.submission.refresh_from_db()
        self.assertEqual(self.submission.score, 15)

        self.ans2.refresh_from_db()
        self.assertEqual(self.ans2.marks_awarded, 10)
        self.assertEqual(self.ans2.feedback, 'Updated feedback.')

    def test_feedback_only_without_marks(self):
        # Teacher can add feedback without assigning marks
        self.client.force_login(self.teacher)
        data = {
            f'marks_{self.q1_mcq.id}': '',
            f'feedback_{self.q1_mcq.id}': 'See me after class.',
            f'marks_{self.q2_short.id}': '10',
        }
        resp = self.client.post(
            reverse('teacher:grading_view', args=[self.submission.id]),
            data,
        )
        self.assertEqual(resp.status_code, 302)

        # Check feedback saved but no marks
        # Note: if student didn't answer, Answer might be created just for feedback
        answers = Answer.objects.filter(
            student_assignment=self.submission, question=self.q1_mcq
        )
        self.assertTrue(answers.exists())
        ans = answers.first()
        self.assertEqual(ans.feedback, 'See me after class.')
        self.assertIsNone(ans.marks_awarded)
