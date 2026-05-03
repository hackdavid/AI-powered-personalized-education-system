"""Tests for Quest (Assignment) grading service."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Role, Tenant, User
from apps.service.models import (
    Answer,
    Assignment,
    Class,
    MissionBrief,
    MissionItem,
    Question,
    StudentAssignment,
    StudentProfile,
    Subject,
)
from apps.service.services.quests import (
    grade_student_assignment,
    save_draft_answers,
    start_attempt,
)


def _ensure_roles():
    Role.objects.get_or_create(
        name=Role.STUDENT, defaults={'display_name': 'Student', 'level': 100},
    )


class QuestGradingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _ensure_roles()
        cls.tenant = Tenant.objects.create(name='Q School', slug='qsch')
        cls.role = Role.objects.get(name=Role.STUDENT)
        cls.subject = Subject.objects.create(
            tenant=cls.tenant, code='MATH', name='Mathematics',
        )
        cls.cls_obj = Class.objects.create(
            tenant=cls.tenant, name='Grade 8-A',
            grade_level=8, section='A', academic_year='2025-2026',
        )

    def _student(self, email='q@t.test'):
        u = User.objects.create_user(
            email=email, password='p', first_name='Q', last_name='S',
            tenant=self.tenant, role=self.role, is_active=True, grade_level=8,
        )
        StudentProfile.objects.get_or_create(student=u)
        return u

    def _assignment(self, total_marks=4, reward_xp=100, due_in_hours=48, **extra):
        due = timezone.now() + timedelta(hours=due_in_hours)
        return Assignment.objects.create(
            tenant=self.tenant, class_obj=self.cls_obj, subject=self.subject,
            title='Test Quest', description='', due_date=due,
            total_marks=total_marks, difficulty=3, reward_xp=reward_xp,
            status=Assignment.STATUS_PUBLISHED,
            **extra,
        )

    def _mcq_q(self, a, order=0, correct='A'):
        return Question.objects.create(
            assignment=a, order=order, question_type=Question.TYPE_MCQ,
            question_text=f'Q{order}: pick A',
            options=[
                {'key': 'A', 'text': 'A'},
                {'key': 'B', 'text': 'B'},
            ],
            correct_answer=correct, marks=1,
        )

    def test_start_attempt_flips_pending_to_in_progress(self):
        u = self._student()
        a = self._assignment()
        self._mcq_q(a)
        sa = start_attempt(u, a)
        self.assertEqual(sa.status, StudentAssignment.STATUS_IN_PROGRESS)
        self.assertIsNotNone(sa.started_at)

    def test_save_draft_answers_upserts(self):
        u = self._student()
        a = self._assignment()
        q1 = self._mcq_q(a, order=0, correct='A')
        q2 = self._mcq_q(a, order=1, correct='B')
        sa = start_attempt(u, a)
        n = save_draft_answers(sa, [
            {'question_id': q1.id, 'selected_option_key': 'A'},
            {'question_id': q2.id, 'selected_option_key': 'A'},
        ])
        self.assertEqual(n, 2)
        self.assertEqual(sa.answers.count(), 2)

        # Upsert: update q2 selection
        save_draft_answers(sa, [
            {'question_id': q2.id, 'selected_option_key': 'B'},
        ])
        a2 = sa.answers.get(question=q2)
        self.assertEqual(a2.selected_option_key, 'B')
        self.assertEqual(sa.answers.count(), 2)

    def test_full_mcq_all_correct_awards_full_xp(self):
        u = self._student()
        a = self._assignment(total_marks=2, reward_xp=100)
        q1 = self._mcq_q(a, order=0, correct='A')
        q2 = self._mcq_q(a, order=1, correct='B')
        sa = start_attempt(u, a)
        save_draft_answers(sa, [
            {'question_id': q1.id, 'selected_option_key': 'A'},
            {'question_id': q2.id, 'selected_option_key': 'B'},
        ])
        sa = grade_student_assignment(sa)
        self.assertEqual(sa.status, StudentAssignment.STATUS_GRADED)
        self.assertEqual(sa.score, 2)
        self.assertEqual(sa.max_score, 2)
        self.assertEqual(sa.xp_awarded, 100)

    def test_partial_mcq_proportional_xp(self):
        u = self._student()
        a = self._assignment(total_marks=4, reward_xp=100)
        q1 = self._mcq_q(a, order=0, correct='A')
        q2 = self._mcq_q(a, order=1, correct='B')
        q3 = self._mcq_q(a, order=2, correct='A')
        q4 = self._mcq_q(a, order=3, correct='B')
        sa = start_attempt(u, a)
        save_draft_answers(sa, [
            {'question_id': q1.id, 'selected_option_key': 'A'},  # correct
            {'question_id': q2.id, 'selected_option_key': 'B'},  # correct
            {'question_id': q3.id, 'selected_option_key': 'B'},  # wrong
            {'question_id': q4.id, 'selected_option_key': 'A'},  # wrong
        ])
        sa = grade_student_assignment(sa)
        self.assertEqual(sa.status, StudentAssignment.STATUS_GRADED)
        self.assertEqual(sa.score, 2)
        self.assertEqual(sa.max_score, 4)
        self.assertEqual(sa.xp_awarded, 50)   # 100 * 2/4

    def test_essay_assignment_stays_submitted_no_xp(self):
        u = self._student()
        a = self._assignment(total_marks=10, reward_xp=200)
        # One MCQ + one essay
        q1 = self._mcq_q(a, order=0, correct='A')
        q2 = Question.objects.create(
            assignment=a, order=1, question_type=Question.TYPE_ESSAY,
            question_text='Write 500 words on X.', marks=9,
        )
        sa = start_attempt(u, a)
        save_draft_answers(sa, [
            {'question_id': q1.id, 'selected_option_key': 'A'},
            {'question_id': q2.id, 'answer_text': 'short essay...'},
        ])
        sa = grade_student_assignment(sa)
        self.assertEqual(sa.status, StudentAssignment.STATUS_SUBMITTED)
        self.assertIsNone(sa.graded_at)
        self.assertEqual(sa.xp_awarded, 0)

    def test_grading_is_idempotent(self):
        u = self._student()
        a = self._assignment(total_marks=1, reward_xp=50)
        q1 = self._mcq_q(a, order=0, correct='A')
        sa = start_attempt(u, a)
        save_draft_answers(sa, [
            {'question_id': q1.id, 'selected_option_key': 'A'},
        ])
        sa = grade_student_assignment(sa)
        first_graded_at = sa.graded_at
        # Second call: must be a no-op
        sa2 = grade_student_assignment(sa)
        self.assertEqual(sa2.graded_at, first_graded_at)

    def test_mission_item_completes_when_assignment_graded(self):
        u = self._student()
        a = self._assignment(total_marks=1, reward_xp=50)
        q1 = self._mcq_q(a, order=0, correct='A')

        # Pre-seed a MissionBrief + MissionItem linked to this assignment for today
        brief = MissionBrief.objects.create(student=u, date=timezone.localdate())
        item = MissionItem.objects.create(
            brief=brief, title='Quest: Test Quest', kind=MissionItem.KIND_QUEST,
            related_object_type='assignment', related_object_id=a.id,
        )

        sa = start_attempt(u, a)
        save_draft_answers(sa, [
            {'question_id': q1.id, 'selected_option_key': 'A'},
        ])
        grade_student_assignment(sa)

        item.refresh_from_db()
        self.assertEqual(item.status, MissionItem.STATUS_COMPLETED)
        self.assertIsNotNone(item.completed_at)
