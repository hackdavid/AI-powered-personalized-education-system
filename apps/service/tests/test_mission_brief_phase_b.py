"""Phase B upgrades to the Mission Brief generator.

These tests cover the new candidate sources (urgent quests, quests,
hunt_tasks, daily_quests) and the helper that auto-completes mission
items when the underlying object is graded/completed.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Role, Tenant, User
from apps.service.models import (
    Assignment,
    Class,
    DailyQuest,
    Goal,
    MissionBrief,
    MissionItem,
    Question,
    StudentAssignment,
    StudentProfile,
    Subject,
    Task,
)
from apps.service.services.missions import (
    ensure_todays_brief,
    generate_mission_brief,
    mark_item_completed_for_event,
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


class MissionBriefPhaseBTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _ensure_roles()
        cls.tenant = Tenant.objects.create(name='MB School', slug='mb')
        cls.role = Role.objects.get(name=Role.STUDENT)
        cls.subject = Subject.objects.create(
            tenant=cls.tenant, code='MATH', name='Mathematics',
        )
        cls.cls_obj = Class.objects.create(
            tenant=cls.tenant, name='Grade 8-A', grade_level=8, section='A',
            academic_year='2025-2026',
        )

    def _student(self, email='mb@t.test'):
        u = User.objects.create_user(
            email=email, password='p', first_name='M', last_name='B',
            tenant=self.tenant, role=self.role, is_active=True, grade_level=8,
        )
        StudentProfile.objects.get_or_create(
            student=u, defaults={'onboarding_complete': True},
        )
        return u

    def _assignment(self, due_in_hours=48, reward_xp=100):
        return Assignment.objects.create(
            tenant=self.tenant, class_obj=self.cls_obj, subject=self.subject,
            title='Test Quest',
            due_date=timezone.now() + timedelta(hours=due_in_hours),
            total_marks=1, reward_xp=reward_xp,
            status=Assignment.STATUS_PUBLISHED,
        )

    def _attempt(self, student, assignment, status=StudentAssignment.STATUS_PENDING):
        return StudentAssignment.objects.create(
            student=student, assignment=assignment,
            status=status, max_score=assignment.total_marks,
        )

    # ------------------------------------------------------------ quest items

    def test_urgent_assignment_surfaces_at_999(self):
        u = self._student()
        a = self._assignment(due_in_hours=6)   # < 24h
        self._attempt(u, a)
        brief = ensure_todays_brief(u)
        items = list(brief.items.all())
        urgent = [i for i in items if i.kind == MissionItem.KIND_URGENT]
        self.assertEqual(len(urgent), 1)
        self.assertEqual(urgent[0].priority, 999)
        self.assertEqual(urgent[0].related_object_type, 'assignment')
        self.assertEqual(urgent[0].related_object_id, a.id)

    def test_nonurgent_assignment_surfaces_as_quest(self):
        u = self._student()
        a = self._assignment(due_in_hours=48)  # 24 <= h < 72 → priority 100
        self._attempt(u, a)
        brief = ensure_todays_brief(u)
        quests = [i for i in brief.items.all() if i.kind == MissionItem.KIND_QUEST]
        self.assertEqual(len(quests), 1)
        self.assertIn(quests[0].priority, (60, 100))

    def test_assignment_far_future_is_priority_60(self):
        u = self._student()
        a = self._assignment(due_in_hours=120)  # > 72h → priority 60
        self._attempt(u, a)
        brief = ensure_todays_brief(u)
        quests = [i for i in brief.items.all() if i.kind == MissionItem.KIND_QUEST]
        self.assertEqual(len(quests), 1)
        self.assertEqual(quests[0].priority, 60)

    # ------------------------------------------------------------ hunt items

    def test_hunt_task_item_from_active_hunt(self):
        u = self._student()
        g = Goal.objects.create(
            student=u, title='My Hunt', description='',
            target_date=timezone.localdate() + timedelta(days=14),
            status=Goal.STATUS_ACTIVE,
        )
        t1 = Task.objects.create(
            goal=g, order=0, title='First', kind=Task.KIND_READ, xp_reward=20,
        )
        Task.objects.create(
            goal=g, order=1, title='Second', kind=Task.KIND_PRACTICE, xp_reward=30,
        )

        brief = ensure_todays_brief(u)
        hunt_items = [i for i in brief.items.all() if i.kind == MissionItem.KIND_HUNT_TASK]
        # At least one hunt_task. (Daily-quests path could add another
        # hunt_task kind; match the "next incomplete task" item specifically
        # by related_object_id.)
        by_task = [i for i in hunt_items if i.related_object_id == t1.id]
        self.assertEqual(len(by_task), 1)
        self.assertEqual(by_task[0].related_object_type, 'hunt_task')
        self.assertEqual(by_task[0].priority, 70)

    # ------------------------------------------------------------ daily-quest items

    def test_daily_quests_surface_in_brief(self):
        u = self._student()
        # Force all four daily quests to exist:
        # mastery → weakest; active hunt → hunt_task DQ; streak_days > 0 → streak
        g = Goal.objects.create(
            student=u, title='H', description='',
            target_date=timezone.localdate() + timedelta(days=14),
            status=Goal.STATUS_ACTIVE,
        )
        Task.objects.create(goal=g, order=0, title='t', kind=Task.KIND_READ)
        p = u.profile
        p.mastery_per_subject = {str(self.subject.id): 15}
        p.streak_days = 3
        p.save()

        brief = ensure_todays_brief(u)
        # Items are capped at 5. Collect by related_object_type='daily_quest'.
        dq_items = [
            i for i in brief.items.all()
            if i.related_object_type == 'daily_quest'
        ]
        # At least 1 (chat visit) must land in; in a no-quest/no-weakest
        # scenario there can be 4 but the cap is 5 across all sources.
        self.assertGreaterEqual(len(dq_items), 1)
        # All DQ items are priority 15 by spec
        for i in dq_items:
            self.assertEqual(i.priority, 15)

    # ------------------------------------------------------------ completion hooks

    def test_grading_marks_mission_item_completed(self):
        u = self._student()
        a = self._assignment(due_in_hours=6)
        # Create a StudentAssignment + minimal MCQ
        sa = self._attempt(u, a)
        q = Question.objects.create(
            assignment=a, order=0, question_type=Question.TYPE_MCQ,
            question_text='Q', options=[{'key': 'A', 'text': 'A'}],
            correct_answer='A', marks=1,
        )
        # Build today's brief (the item should appear)
        brief = ensure_todays_brief(u)
        item = brief.items.filter(
            related_object_type='assignment', related_object_id=a.id,
        ).first()
        self.assertIsNotNone(item)
        self.assertEqual(item.status, MissionItem.STATUS_PENDING)

        # Grade it — the helper should mark the mission item as completed
        sa = start_attempt(u, a)
        save_draft_answers(sa, [{'question_id': q.id, 'selected_option_key': 'A'}])
        grade_student_assignment(sa)

        item.refresh_from_db()
        self.assertEqual(item.status, MissionItem.STATUS_COMPLETED)

    def test_helper_marks_hunt_task_item_completed(self):
        u = self._student()
        g = Goal.objects.create(
            student=u, title='Hunt', description='',
            target_date=timezone.localdate() + timedelta(days=14),
            status=Goal.STATUS_ACTIVE,
        )
        t = Task.objects.create(
            goal=g, order=0, title='Read', kind=Task.KIND_READ, xp_reward=20,
        )

        brief = ensure_todays_brief(u)
        item = brief.items.filter(
            related_object_type='hunt_task', related_object_id=t.id,
        ).first()
        self.assertIsNotNone(item)

        # Simulate what the view will do when a task is completed
        updated = mark_item_completed_for_event(u, 'hunt_task', t.id)
        self.assertTrue(updated)

        item.refresh_from_db()
        self.assertEqual(item.status, MissionItem.STATUS_COMPLETED)

    def test_helper_returns_false_when_no_matching_item(self):
        u = self._student()
        brief = MissionBrief.objects.create(student=u, date=timezone.localdate())
        MissionItem.objects.create(
            brief=brief, title='t', kind=MissionItem.KIND_CHAT, xp_reward=1,
        )
        updated = mark_item_completed_for_event(u, 'assignment', 99999)
        self.assertFalse(updated)
