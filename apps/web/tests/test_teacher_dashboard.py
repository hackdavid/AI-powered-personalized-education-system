"""Tests for the teacher dashboard ("Mission Control")."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, Tenant, User
from apps.service.models import (
    Assignment,
    Class,
    ClassSubject,
    Enrollment,
    Question,
    StudentAssignment,
    StudentProfile,
    Subject,
    XPLedger,
)
from apps.web.views.dashboards import _teacher_status_context


def _ensure_roles():
    Role.objects.get_or_create(
        name=Role.TEACHER, defaults={'display_name': 'Teacher', 'level': 50})
    Role.objects.get_or_create(
        name=Role.STUDENT, defaults={'display_name': 'Student', 'level': 100})


class TeacherDashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _ensure_roles()
        cls.tenant = Tenant.objects.create(name='Dash Teacher School', slug='dts')
        cls.other_tenant = Tenant.objects.create(name='Other School', slug='other')
        cls.teacher_role = Role.objects.get(name=Role.TEACHER)
        cls.student_role = Role.objects.get(name=Role.STUDENT)
        cls.subject = Subject.objects.create(
            tenant=cls.tenant, code='SCI', name='Science')

    # ---- helpers ----

    def _make_teacher(self, email='t@dts.test', tenant=None):
        return User.objects.create_user(
            email=email, password='p', first_name='Theo', last_name='Teacher',
            tenant=tenant or self.tenant, role=self.teacher_role,
            is_active=True, employee_id=f'E{User.objects.count()}',
        )

    def _make_student(self, email, tenant=None):
        u = User.objects.create_user(
            email=email, password='p', first_name='Stu', last_name='Dent',
            tenant=tenant or self.tenant, role=self.student_role,
            is_active=True, student_id=f'S{User.objects.count()}',
        )
        StudentProfile.objects.create(student=u)
        return u

    def _make_class(self, teacher, name='G8A', tenant=None, grade=8, section=None):
        # Use a unique section per Class to avoid the
        # (tenant, grade, section, academic_year) unique constraint when a
        # single test creates multiple classes in the same tenant.
        if section is None:
            section = chr(65 + Class.objects.count())  # A, B, C, ...
        cls = Class.objects.create(
            tenant=tenant or self.tenant, name=name,
            grade_level=grade, section=section,
            academic_year='2025-2026', class_teacher=teacher,
        )
        ClassSubject.objects.create(class_obj=cls, subject=self.subject, teacher=teacher)
        return cls

    # ---- tests ----

    def test_dashboard_redirects_anonymous_to_login(self):
        resp = self.client.get(reverse('teacher:dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/auth/login', resp.url)

    def test_dashboard_renders_for_teacher_with_no_classes(self):
        t = self._make_teacher()
        self.client.force_login(t)
        resp = self.client.get(reverse('teacher:dashboard'))
        self.assertEqual(resp.status_code, 200)
        # Empty-state messaging should mention they have no classes
        self.assertIn(b'not assigned to any classes', resp.content)
        # Stat cards still render with zero values
        self.assertIn(b'Total Students', resp.content)
        self.assertIn(b'Active Quests', resp.content)

    def test_stats_count_students_classes_and_assignments(self):
        teacher = self._make_teacher()
        cls = self._make_class(teacher)

        # Enrol 3 students
        students = [self._make_student(f's{i}@dts.test') for i in range(3)]
        for s in students:
            Enrollment.objects.create(class_obj=cls, student=s, is_active=True)

        # 1 published quest (active), 1 draft, 1 archived
        now = timezone.now()
        Assignment.objects.create(
            tenant=self.tenant, class_obj=cls, subject=self.subject,
            title='Live', due_date=now + timedelta(days=3),
            status=Assignment.STATUS_PUBLISHED, total_marks=5,
        )
        Assignment.objects.create(
            tenant=self.tenant, class_obj=cls, subject=self.subject,
            title='Draft', due_date=now + timedelta(days=3),
            status=Assignment.STATUS_DRAFT, total_marks=5,
        )
        Assignment.objects.create(
            tenant=self.tenant, class_obj=cls, subject=self.subject,
            title='Old', due_date=now - timedelta(days=10),
            status=Assignment.STATUS_PUBLISHED, total_marks=5,  # past-due, NOT counted
        )

        ctx = _teacher_status_context(teacher)
        self.assertEqual(ctx['stats']['total_students'], 3)
        self.assertEqual(ctx['stats']['total_classes'], 1)
        self.assertEqual(ctx['stats']['active_assignments'], 1)

    def test_pending_reviews_counts_only_submitted_unscored(self):
        teacher = self._make_teacher()
        cls = self._make_class(teacher)
        student = self._make_student('p1@dts.test')
        Enrollment.objects.create(class_obj=cls, student=student, is_active=True)

        a = Assignment.objects.create(
            tenant=self.tenant, class_obj=cls, subject=self.subject,
            title='Q', due_date=timezone.now() + timedelta(days=1),
            status=Assignment.STATUS_PUBLISHED, total_marks=5,
        )
        # Submitted (counts)
        StudentAssignment.objects.create(
            assignment=a, student=student,
            status=StudentAssignment.STATUS_SUBMITTED, max_score=5,
        )
        # In progress (does NOT count)
        s2 = self._make_student('p2@dts.test')
        Enrollment.objects.create(class_obj=cls, student=s2, is_active=True)
        StudentAssignment.objects.create(
            assignment=a, student=s2,
            status=StudentAssignment.STATUS_IN_PROGRESS, max_score=5,
        )
        # Already graded (does NOT count as pending review)
        s3 = self._make_student('p3@dts.test')
        Enrollment.objects.create(class_obj=cls, student=s3, is_active=True)
        StudentAssignment.objects.create(
            assignment=a, student=s3,
            status=StudentAssignment.STATUS_GRADED, score=5, max_score=5,
        )

        ctx = _teacher_status_context(teacher)
        self.assertEqual(ctx['stats']['pending_reviews'], 1)

    def test_avg_mastery_aggregates_across_subjects_and_students(self):
        teacher = self._make_teacher()
        cls = self._make_class(teacher)

        # 2 students with mastery data
        s1 = self._make_student('m1@dts.test')
        s2 = self._make_student('m2@dts.test')
        Enrollment.objects.create(class_obj=cls, student=s1, is_active=True)
        Enrollment.objects.create(class_obj=cls, student=s2, is_active=True)
        s1.profile.mastery_per_subject = {str(self.subject.id): 80, '99': 60}
        s1.profile.save(update_fields=['mastery_per_subject'])
        s2.profile.mastery_per_subject = {str(self.subject.id): 40}
        s2.profile.save(update_fields=['mastery_per_subject'])

        ctx = _teacher_status_context(teacher)
        # (80 + 60 + 40) / 3 = 60
        self.assertEqual(ctx['stats']['avg_mastery_pct'], 60)

    def test_avg_mastery_zero_when_no_data(self):
        teacher = self._make_teacher()
        self._make_class(teacher)  # no students enrolled
        ctx = _teacher_status_context(teacher)
        self.assertEqual(ctx['stats']['avg_mastery_pct'], 0)

    def test_recent_activity_only_includes_my_students(self):
        teacher = self._make_teacher()
        cls = self._make_class(teacher)
        my_student = self._make_student('mine@dts.test')
        Enrollment.objects.create(class_obj=cls, student=my_student, is_active=True)

        # Another teacher / class / student (different teacher in same tenant)
        other_teacher = self._make_teacher('other@dts.test')
        other_cls = self._make_class(other_teacher, name='G9B')
        not_my_student = self._make_student('notmine@dts.test')
        Enrollment.objects.create(class_obj=other_cls, student=not_my_student, is_active=True)

        XPLedger.objects.create(
            student=my_student, source=XPLedger.SOURCE_QUEST, amount=50,
            description='My student finished a quest',
        )
        XPLedger.objects.create(
            student=not_my_student, source=XPLedger.SOURCE_QUEST, amount=50,
            description='Not my student',
        )

        ctx = _teacher_status_context(teacher)
        self.assertEqual(len(ctx['recent_activity']), 1)
        self.assertEqual(ctx['recent_activity'][0]['student_name'], my_student.get_full_name())

    def test_classes_isolated_by_tenant(self):
        teacher = self._make_teacher()
        self._make_class(teacher)  # in cls.tenant

        # Another teacher in OTHER tenant — students/classes there must be invisible
        other_teacher = self._make_teacher('other@other.test', tenant=self.other_tenant)
        other_cls = Class.objects.create(
            tenant=self.other_tenant, name='G9X', grade_level=9, section='X',
            academic_year='2025-2026', class_teacher=other_teacher,
        )
        sneaky_student = User.objects.create_user(
            email='sneaky@other.test', password='p', first_name='S', last_name='X',
            tenant=self.other_tenant, role=self.student_role,
            is_active=True, student_id='SN1',
        )
        StudentProfile.objects.create(student=sneaky_student)
        Enrollment.objects.create(
            class_obj=other_cls, student=sneaky_student, is_active=True,
        )

        ctx = _teacher_status_context(teacher)
        # Teacher should see only their 1 own class & 0 students; nothing leaks across tenants
        self.assertEqual(ctx['stats']['total_classes'], 1)
        self.assertEqual(ctx['stats']['total_students'], 0)
        class_names = [c['name'] for c in ctx['classes']]
        self.assertNotIn('G9X', class_names)

    def test_class_card_data_shape(self):
        teacher = self._make_teacher()
        cls = self._make_class(teacher, name='Grade-7-Alpha')
        for i in range(2):
            s = self._make_student(f'cc{i}@dts.test')
            Enrollment.objects.create(class_obj=cls, student=s, is_active=True)

        Assignment.objects.create(
            tenant=self.tenant, class_obj=cls, subject=self.subject,
            title='Live', due_date=timezone.now() + timedelta(days=1),
            status=Assignment.STATUS_PUBLISHED, total_marks=5,
        )

        ctx = _teacher_status_context(teacher)
        self.assertEqual(len(ctx['classes']), 1)
        card = ctx['classes'][0]
        self.assertEqual(card['name'], 'Grade-7-Alpha')
        self.assertEqual(card['student_count'], 2)
        self.assertEqual(card['active_quest_count'], 1)
        self.assertTrue(card['is_homeroom'])

    def test_subject_teacher_sees_class_even_if_not_homeroom(self):
        # Homeroom is held by teacher_a; teacher_b only teaches the subject in
        # that class via ClassSubject. teacher_b should still see the class.
        teacher_a = self._make_teacher('a@dts.test')
        teacher_b = self._make_teacher('b@dts.test')
        cls = Class.objects.create(
            tenant=self.tenant, name='G6A', grade_level=6, section='A',
            academic_year='2025-2026', class_teacher=teacher_a,
        )
        ClassSubject.objects.create(class_obj=cls, subject=self.subject, teacher=teacher_b)

        ctx_a = _teacher_status_context(teacher_a)
        ctx_b = _teacher_status_context(teacher_b)
        self.assertEqual(ctx_a['stats']['total_classes'], 1)
        self.assertEqual(ctx_b['stats']['total_classes'], 1)
        self.assertTrue(ctx_a['classes'][0]['is_homeroom'])
        self.assertFalse(ctx_b['classes'][0]['is_homeroom'])
