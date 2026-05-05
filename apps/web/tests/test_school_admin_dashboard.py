"""Tests for School Admin Dashboard, Analytics, and Enrollment Management.

Tests all three main views:
1. Dashboard - stats cards, recent activity, alerts
2. Analytics - teacher utilization, class performance, subject distribution
3. Enrollment - unenrolled students, class capacity management
"""

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
    StudentAssignment,
    StudentProfile,
    Subject,
)


def _ensure_roles():
    Role.objects.get_or_create(
        name=Role.SCHOOL_ADMIN, defaults={'display_name': 'School Admin', 'level': 10})
    Role.objects.get_or_create(
        name=Role.TEACHER, defaults={'display_name': 'Teacher', 'level': 50})
    Role.objects.get_or_create(
        name=Role.STUDENT, defaults={'display_name': 'Student', 'level': 100})


class SchoolAdminFixtureMixin:
    """Shared setup: admin, teachers, students, classes, and varied data."""

    @classmethod
    def setUpTestData(cls):
        _ensure_roles()
        cls.tenant = Tenant.objects.get_or_create(name='Admin School', slug='admin-school')[0]
        cls.admin_role = Role.objects.get(name=Role.SCHOOL_ADMIN)
        cls.teacher_role = Role.objects.get(name=Role.TEACHER)
        cls.student_role = Role.objects.get(name=Role.STUDENT)

        # School admin
        cls.admin = cls._mk_admin('admin@admin.test')

        # Subjects
        cls.subject1 = Subject.objects.create(tenant=cls.tenant, code='MATH', name='Mathematics')
        cls.subject2 = Subject.objects.create(tenant=cls.tenant, code='SCI', name='Science')
        cls.subject3 = Subject.objects.create(tenant=cls.tenant, code='ENG', name='English')

        # Teachers
        cls.teacher1 = cls._mk_teacher('teacher1@admin.test', 'Alice', 'Smith')
        cls.teacher2 = cls._mk_teacher('teacher2@admin.test', 'Bob', 'Jones')
        cls.teacher3 = cls._mk_teacher('teacher3@admin.test', 'Carol', 'White')

        # Set teacher3 as inactive (last_login > 30 days ago)
        cls.teacher3.last_login = timezone.now() - timedelta(days=35)
        cls.teacher3.save()

        # Classes
        cls.class1 = cls._mk_class(cls.teacher1, 'Grade 10A', 10)
        cls.class2 = cls._mk_class(cls.teacher2, 'Grade 11B', 11)
        cls.class3 = cls._mk_class(None, 'Grade 9C', 9)  # No teacher assigned

        # Students
        cls.students = []
        for i in range(40):
            student = cls._mk_student(f'student{i}@admin.test', f'Student{i}', 'Test')
            cls.students.append(student)

        # Enroll students: 20 in class1, 15 in class2, 5 not enrolled
        for i in range(20):
            Enrollment.objects.create(class_obj=cls.class1, student=cls.students[i], is_active=True)
        for i in range(20, 35):
            Enrollment.objects.create(class_obj=cls.class2, student=cls.students[i], is_active=True)

        # Create student profiles for first 35 students
        for i in range(35):
            StudentProfile.objects.create(
                student=cls.students[i],
                level=5,
                total_xp=500,
                streak_days=7,
                last_active_date=timezone.now().date(),
                mastery_per_subject={
                    str(cls.subject1.id): 70,
                    str(cls.subject2.id): 65,
                },
            )

        # Create some quests
        now = timezone.now()
        cls.quest1 = Assignment.objects.create(
            tenant=cls.tenant,
            class_obj=cls.class1,
            subject=cls.subject1,
            title='Math Quest 1',
            due_date=now + timedelta(days=7),
            status='published',
            total_marks=100,
            created_by=cls.teacher1,
            updated_by=cls.teacher1,
        )

        cls.quest2 = Assignment.objects.create(
            tenant=cls.tenant,
            class_obj=cls.class2,
            subject=cls.subject2,
            title='Science Quest 1',
            due_date=now + timedelta(days=5),
            status='published',
            total_marks=100,
            created_by=cls.teacher2,
            updated_by=cls.teacher2,
        )

        # Create some submissions this week
        week_ago = now - timedelta(days=3)
        for i in range(10):
            StudentAssignment.objects.create(
                assignment=cls.quest1,
                student=cls.students[i],
                status='graded',
                score=80,
                max_score=100,
                submitted_at=week_ago,
            )

    @classmethod
    def _mk_admin(cls, email):
        return User.objects.create_user(
            email=email, password='p', first_name='Admin', last_name='User',
            tenant=cls.tenant, role=cls.admin_role,
            is_active=True, employee_id=f'A{User.objects.count()}',
        )

    @classmethod
    def _mk_teacher(cls, email, first='T', last='X'):
        return User.objects.create_user(
            email=email, password='p', first_name=first, last_name=last,
            tenant=cls.tenant, role=cls.teacher_role,
            is_active=True, employee_id=f'T{User.objects.count()}',
        )

    @classmethod
    def _mk_student(cls, email, first='S', last='X'):
        return User.objects.create_user(
            email=email, password='p', first_name=first, last_name=last,
            tenant=cls.tenant, role=cls.student_role,
            is_active=True, student_id=f'S{User.objects.count()}',
        )

    @classmethod
    def _mk_class(cls, teacher, name, grade):
        section = chr(65 + Class.objects.count() % 26)
        c = Class.objects.create(
            tenant=cls.tenant, name=name,
            grade_level=grade, section=section,
            academic_year='2025-2026',
            class_teacher=teacher,
        )
        return c


# ---------------------------------------------------------------------------
# Dashboard View Tests
# ---------------------------------------------------------------------------


class DashboardViewTests(SchoolAdminFixtureMixin, TestCase):
    def test_anonymous_redirects_to_login(self):
        resp = self.client.get(reverse('school_admin:dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp.url)

    def test_teacher_cannot_access(self):
        self.client.force_login(self.teacher1)
        resp = self.client.get(reverse('school_admin:dashboard'))
        self.assertEqual(resp.status_code, 302)  # Redirects to dashboard
        self.assertIn('dashboard', resp.url)

    def test_student_cannot_access(self):
        self.client.force_login(self.students[0])
        resp = self.client.get(reverse('school_admin:dashboard'))
        self.assertEqual(resp.status_code, 302)  # Redirects to dashboard
        self.assertIn('dashboard', resp.url)

    def test_admin_sees_dashboard(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('school_admin:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'school_admin/dashboard.html')

    def test_stats_cards_display(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('school_admin:dashboard'))

        stats = resp.context['stats']
        self.assertEqual(stats['total_students'], 40)
        self.assertEqual(stats['total_teachers'], 3)
        self.assertEqual(stats['total_classes'], 3)
        self.assertEqual(stats['active_quests'], 2)

    def test_recent_activity_feed(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('school_admin:dashboard'))

        recent_activity = resp.context['recent_activity']
        self.assertGreater(len(recent_activity), 0)

        # Should have timestamps
        for activity in recent_activity:
            self.assertIn('timestamp', activity)
            self.assertIn('text', activity)


# ---------------------------------------------------------------------------
# Dashboard Alerts Tests
# ---------------------------------------------------------------------------


class DashboardAlertsTests(SchoolAdminFixtureMixin, TestCase):
    def test_alert_for_class_without_teacher(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('school_admin:dashboard'))

        alerts = resp.context['alerts']
        alert_messages = [a['message'] for a in alerts]

        # Should alert about class3 having no teacher
        self.assertTrue(
            any('no teacher assigned' in msg for msg in alert_messages)
        )

    def test_alert_for_unenrolled_students(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('school_admin:dashboard'))

        alerts = resp.context['alerts']
        alert_messages = [a['message'] for a in alerts]

        # Should alert about 5 unenrolled students
        self.assertTrue(
            any('not enrolled' in msg for msg in alert_messages)
        )

    def test_alert_for_inactive_teachers(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('school_admin:dashboard'))

        alerts = resp.context['alerts']
        alert_messages = [a['message'] for a in alerts]

        # Should alert about teacher3 being inactive
        self.assertTrue(
            any('inactive for 30+ days' in msg for msg in alert_messages)
        )

    def test_no_alerts_when_everything_ok(self):
        # Fix all issues: assign teacher to class3, enroll all students, update teacher3 login
        self.class3.class_teacher = self.teacher1
        self.class3.save()

        for student in self.students[35:]:
            Enrollment.objects.create(class_obj=self.class1, student=student, is_active=True)

        self.teacher3.last_login = timezone.now()
        self.teacher3.save()

        self.client.force_login(self.admin)
        resp = self.client.get(reverse('school_admin:dashboard'))

        alerts = resp.context['alerts']
        # Should have fewer or no alerts now
        self.assertLessEqual(len(alerts), 1)  # Might still have oversized class alert


# ---------------------------------------------------------------------------
# Analytics View Tests
# ---------------------------------------------------------------------------


class AnalyticsViewTests(SchoolAdminFixtureMixin, TestCase):
    def test_anonymous_redirects_to_login(self):
        resp = self.client.get(reverse('school_admin:analytics'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp.url)

    def test_admin_sees_analytics(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('school_admin:analytics'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'school_admin/analytics.html')

    def test_teacher_utilization_data(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('school_admin:analytics'))

        utilization = resp.context['teacher_utilization']
        self.assertEqual(len(utilization), 3)

        # Check structure
        for item in utilization:
            self.assertIn('teacher', item)
            self.assertIn('classes', item)
            self.assertIn('students', item)
            self.assertIn('quests_published', item)

    def test_class_performance_comparison(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('school_admin:analytics'))

        performance = resp.context['class_performance']
        self.assertGreaterEqual(len(performance), 2)

        # Check structure
        for item in performance:
            self.assertIn('class', item)
            self.assertIn('student_count', item)
            self.assertIn('avg_mastery', item)

    def test_subject_distribution(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('school_admin:analytics'))

        distribution = resp.context['subject_distribution']
        self.assertEqual(len(distribution), 3)  # 3 subjects created

        # Check structure
        for item in distribution:
            self.assertIn('subject', item)
            self.assertIn('class_count', item)


# ---------------------------------------------------------------------------
# Enrollment Management Tests
# ---------------------------------------------------------------------------


class EnrollmentViewTests(SchoolAdminFixtureMixin, TestCase):
    def test_anonymous_redirects_to_login(self):
        resp = self.client.get(reverse('school_admin:enrollment'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp.url)

    def test_admin_sees_enrollment(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('school_admin:enrollment'))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'school_admin/enrollment.html')

    def test_unenrolled_students_list(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('school_admin:enrollment'))

        unenrolled = resp.context['unenrolled_students']
        self.assertEqual(len(unenrolled), 5)  # 5 students not enrolled

        # Check they are the right students (35-39)
        unenrolled_ids = [s.id for s in unenrolled]
        for i in range(35, 40):
            self.assertIn(self.students[i].id, unenrolled_ids)

    def test_class_sizes_displayed(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('school_admin:enrollment'))

        class_sizes = resp.context['class_sizes']
        self.assertEqual(len(class_sizes), 3)

        # Check class1 has 20 students
        class1_info = next(c for c in class_sizes if c['class'].id == self.class1.id)
        self.assertEqual(class1_info['size'], 20)
        self.assertEqual(class1_info['status'], 'optimal')

        # Check class2 has 15 students
        class2_info = next(c for c in class_sizes if c['class'].id == self.class2.id)
        self.assertEqual(class2_info['size'], 15)
        self.assertEqual(class2_info['status'], 'under')

    def test_oversized_class_flagged(self):
        # Enroll 36 students in class1 (need to create more students)
        for i in range(20):
            student = self._mk_student(f'extra{i}@admin.test', f'Extra{i}', 'Student')
            Enrollment.objects.create(class_obj=self.class1, student=student, is_active=True)

        self.client.force_login(self.admin)
        resp = self.client.get(reverse('school_admin:enrollment'))

        class_sizes = resp.context['class_sizes']
        class1_info = next(c for c in class_sizes if c['class'].id == self.class1.id)
        self.assertEqual(class1_info['status'], 'over')


# ---------------------------------------------------------------------------
# Dashboard Stats Calculation Tests
# ---------------------------------------------------------------------------


class StatsCalculationTests(SchoolAdminFixtureMixin, TestCase):
    def test_counts_only_active_users(self):
        # Deactivate a student
        self.students[0].is_active = False
        self.students[0].save()

        self.client.force_login(self.admin)
        resp = self.client.get(reverse('school_admin:dashboard'))

        stats = resp.context['stats']
        self.assertEqual(stats['total_students'], 39)  # 40 - 1 inactive

    def test_weekly_additions(self):
        # Create a student added this week
        new_student = self._mk_student('newstudent@admin.test', 'New', 'Student')
        new_student.created_at = timezone.now() - timedelta(days=2)
        new_student.save()

        self.client.force_login(self.admin)
        resp = self.client.get(reverse('school_admin:dashboard'))

        stats = resp.context['stats']
        self.assertGreaterEqual(stats['students_added_this_week'], 1)

    def test_submissions_this_week(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('school_admin:dashboard'))

        stats = resp.context['stats']
        self.assertEqual(stats['submissions_this_week'], 10)  # 10 submissions created

    def test_active_quests_count(self):
        # Create an expired quest
        past = timezone.now() - timedelta(days=10)
        Assignment.objects.create(
            tenant=self.tenant,
            class_obj=self.class1,
            subject=self.subject1,
            title='Expired Quest',
            due_date=past,
            status='published',
            total_marks=100,
            created_by=self.teacher1,
            updated_by=self.teacher1,
        )

        self.client.force_login(self.admin)
        resp = self.client.get(reverse('school_admin:dashboard'))

        stats = resp.context['stats']
        self.assertEqual(stats['active_quests'], 2)  # Only future quests


# ---------------------------------------------------------------------------
# Multi-Tenant Isolation Tests
# ---------------------------------------------------------------------------


class MultiTenantIsolationTests(SchoolAdminFixtureMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        # Create another tenant with data
        cls.other_tenant = Tenant.objects.create(name='Other School', slug='other-school')
        cls.other_admin = User.objects.create_user(
            email='other_admin@other.test',
            password='p',
            first_name='Other',
            last_name='Admin',
            tenant=cls.other_tenant,
            role=cls.admin_role,
            is_active=True,
            employee_id='OA1',
        )

        # Create some data in other tenant
        other_teacher = User.objects.create_user(
            email='other_teacher@other.test',
            password='p',
            first_name='Other',
            last_name='Teacher',
            tenant=cls.other_tenant,
            role=cls.teacher_role,
            is_active=True,
            employee_id='OT1',
        )

        Class.objects.create(
            tenant=cls.other_tenant,
            name='Other Class',
            grade_level=10,
            section='X',
            academic_year='2025-2026',
            class_teacher=other_teacher,
        )

    def test_admin_sees_only_own_tenant_students(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('school_admin:dashboard'))

        stats = resp.context['stats']
        self.assertEqual(stats['total_students'], 40)  # Not other tenant's students

    def test_admin_sees_only_own_tenant_classes(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse('school_admin:dashboard'))

        stats = resp.context['stats']
        self.assertEqual(stats['total_classes'], 3)  # Not other tenant's class

    def test_other_admin_sees_different_data(self):
        self.client.force_login(self.other_admin)
        resp = self.client.get(reverse('school_admin:dashboard'))

        stats = resp.context['stats']
        self.assertEqual(stats['total_students'], 0)
        self.assertEqual(stats['total_teachers'], 1)
        self.assertEqual(stats['total_classes'], 1)
