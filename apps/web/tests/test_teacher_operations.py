"""Phase E: tests for the teacher Class / Student / Gradebook pages.

The whole suite shares the same fixture (`PhaseEFixtureMixin`) because each
view operates on the same teacher↔class↔student↔assignment relationship.
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
    Goal,
    Question,
    StudentAssignment,
    StudentProfile,
    Subject,
    XPLedger,
)


def _ensure_roles():
    Role.objects.get_or_create(
        name=Role.TEACHER, defaults={'display_name': 'Teacher', 'level': 50})
    Role.objects.get_or_create(
        name=Role.STUDENT, defaults={'display_name': 'Student', 'level': 100})


class PhaseEFixtureMixin:
    """Shared setup: one teacher, one class with three enrolled students,
    one published quest with mixed submissions; a separate teacher in the
    same tenant who owns a different class with their own student.
    """

    @classmethod
    def setUpTestData(cls):
        _ensure_roles()
        cls.tenant = Tenant.objects.create(name='Phase E School', slug='pes')
        cls.other_tenant = Tenant.objects.create(name='Other Phase E School', slug='oes')
        cls.teacher_role = Role.objects.get(name=Role.TEACHER)
        cls.student_role = Role.objects.get(name=Role.STUDENT)
        cls.subject = Subject.objects.create(
            tenant=cls.tenant, code='SCI', name='Science')
        cls.other_subject = Subject.objects.create(
            tenant=cls.tenant, code='ENG', name='English')

        cls.teacher = cls._mk_teacher('me@pes.test')
        cls.other_teacher = cls._mk_teacher('other@pes.test')
        cls.cross_tenant_teacher = cls._mk_teacher(
            'cross@oes.test', tenant=cls.other_tenant,
        )

        # MY class (homeroom + subject)
        cls.my_class = cls._mk_class(cls.teacher, name='Grade 8 Alpha')
        cls.alice = cls._mk_student('alice@pes.test', first='Alice', last='A')
        cls.bob = cls._mk_student('bob@pes.test', first='Bob', last='B')
        cls.cara = cls._mk_student('cara@pes.test', first='Cara', last='C')
        for s in [cls.alice, cls.bob, cls.cara]:
            Enrollment.objects.create(class_obj=cls.my_class, student=s, is_active=True)

        # Other teacher's class (same tenant, no overlap)
        cls.other_class = cls._mk_class(cls.other_teacher, name='Grade 9 Beta')
        cls.dave = cls._mk_student('dave@pes.test', first='Dave', last='D')
        Enrollment.objects.create(class_obj=cls.other_class, student=cls.dave, is_active=True)

        # A published quest in MY class with mixed submissions
        now = timezone.now()
        cls.published_quest = Assignment.objects.create(
            tenant=cls.tenant, class_obj=cls.my_class, subject=cls.subject,
            title='Photosynthesis Quiz', due_date=now + timedelta(days=7),
            status=Assignment.STATUS_PUBLISHED, total_marks=10,
            created_by=cls.teacher, updated_by=cls.teacher,
        )
        Question.objects.create(
            assignment=cls.published_quest, order=0, question_type='mcq',
            question_text='What gas?', options=[{'key': 'A', 'text': 'O2'}],
            correct_answer='A', marks=10,
        )
        # Alice graded 8/10, Bob submitted (no score), Cara never started.
        StudentAssignment.objects.create(
            assignment=cls.published_quest, student=cls.alice,
            status=StudentAssignment.STATUS_GRADED, score=8, max_score=10,
        )
        StudentAssignment.objects.create(
            assignment=cls.published_quest, student=cls.bob,
            status=StudentAssignment.STATUS_SUBMITTED, max_score=10,
        )

        # XP events for activity feed
        XPLedger.objects.create(
            student=cls.alice, source=XPLedger.SOURCE_QUEST, amount=80,
            description='Photosynthesis Quiz',
        )
        XPLedger.objects.create(
            student=cls.dave, source=XPLedger.SOURCE_QUEST, amount=99,
            description='Should NOT be visible to me',
        )

    # ---- factories ----

    @classmethod
    def _mk_teacher(cls, email, tenant=None):
        return User.objects.create_user(
            email=email, password='p', first_name='T', last_name='X',
            tenant=tenant or cls.tenant, role=cls.teacher_role,
            is_active=True, employee_id=f'E{User.objects.count()}',
        )

    @classmethod
    def _mk_student(cls, email, first='S', last='X', tenant=None):
        u = User.objects.create_user(
            email=email, password='p', first_name=first, last_name=last,
            tenant=tenant or cls.tenant, role=cls.student_role,
            is_active=True, student_id=f'S{User.objects.count()}',
        )
        StudentProfile.objects.create(student=u, level=2, total_xp=120)
        return u

    @classmethod
    def _mk_class(cls, teacher, name, tenant=None, grade=None, section=None):
        if section is None:
            section = chr(65 + Class.objects.count())
        if grade is None:
            grade = 8 + (Class.objects.count() % 5)
        c = Class.objects.create(
            tenant=tenant or cls.tenant, name=name,
            grade_level=grade, section=section,
            academic_year='2025-2026', class_teacher=teacher,
        )
        ClassSubject.objects.create(class_obj=c, subject=cls.subject, teacher=teacher)
        return c


# ---------------------------------------------------------------------------
# CLASS list + detail
# ---------------------------------------------------------------------------


class ClassListTests(PhaseEFixtureMixin, TestCase):
    def test_anonymous_redirects_to_login(self):
        resp = self.client.get(reverse('teacher:class_list'))
        self.assertEqual(resp.status_code, 302)

    def test_lists_only_my_classes(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse('teacher:class_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Grade 8 Alpha')
        # Other teacher's class should NOT appear
        self.assertNotContains(resp, 'Grade 9 Beta')

    def test_other_teachers_class_visible_to_them_not_to_me(self):
        self.client.force_login(self.other_teacher)
        resp = self.client.get(reverse('teacher:class_list'))
        self.assertContains(resp, 'Grade 9 Beta')
        self.assertNotContains(resp, 'Grade 8 Alpha')


class ClassDetailTests(PhaseEFixtureMixin, TestCase):
    def test_renders_for_owning_teacher(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(
            reverse('teacher:class_detail', args=[self.my_class.id])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Grade 8 Alpha')
        self.assertContains(resp, 'Alice A')
        self.assertContains(resp, 'Bob B')
        self.assertContains(resp, 'Cara C')

    def test_other_teachers_class_returns_404(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(
            reverse('teacher:class_detail', args=[self.other_class.id])
        )
        self.assertEqual(resp.status_code, 404)

    def test_cross_tenant_class_returns_404(self):
        # Make a class in the other tenant; my teacher should not see it.
        other = Class.objects.create(
            tenant=self.other_tenant, name='X', grade_level=10, section='Z',
            academic_year='2025-2026', class_teacher=self.cross_tenant_teacher,
        )
        self.client.force_login(self.teacher)
        resp = self.client.get(
            reverse('teacher:class_detail', args=[other.id])
        )
        self.assertEqual(resp.status_code, 404)

    def test_recent_activity_scoped_to_this_class(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(
            reverse('teacher:class_detail', args=[self.my_class.id])
        )
        # Alice's XP event from MY class shows
        self.assertContains(resp, 'Alice A')
        # Dave's XP event (not in my class) does NOT
        self.assertNotContains(resp, 'NOT be visible')


# ---------------------------------------------------------------------------
# STUDENT list + detail
# ---------------------------------------------------------------------------


class StudentListTests(PhaseEFixtureMixin, TestCase):
    def test_lists_my_students_only(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse('teacher:student_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Alice A')
        self.assertContains(resp, 'Bob B')
        self.assertContains(resp, 'Cara C')
        self.assertNotContains(resp, 'Dave D')  # not in any of my classes

    def test_class_filter_narrows_results(self):
        self.client.force_login(self.teacher)
        # Make a SECOND class with one of my own students duplicated
        c2 = self._mk_class(self.teacher, name='Math 8B')
        Enrollment.objects.create(class_obj=c2, student=self.alice, is_active=True)
        eve = self._mk_student('eve@pes.test', first='Eve', last='E')
        Enrollment.objects.create(class_obj=c2, student=eve, is_active=True)

        resp = self.client.get(reverse('teacher:student_list') + f'?class={c2.id}')
        self.assertContains(resp, 'Alice A')
        self.assertContains(resp, 'Eve E')
        self.assertNotContains(resp, 'Bob B')
        self.assertNotContains(resp, 'Cara C')

    def test_class_filter_silently_ignores_unknown_class(self):
        self.client.force_login(self.teacher)
        # Filter by a class NOT mine — should fall back to "all my students"
        resp = self.client.get(
            reverse('teacher:student_list') + f'?class={self.other_class.id}'
        )
        self.assertEqual(resp.status_code, 200)
        # Should show ALL my students (filter ignored), not other_class's roster
        self.assertContains(resp, 'Alice A')
        self.assertNotContains(resp, 'Dave D')


class StudentDetailTests(PhaseEFixtureMixin, TestCase):
    def test_renders_my_student(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(
            reverse('teacher:student_detail', args=[self.alice.id])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Alice A')
        self.assertContains(resp, 'Total XP')
        # Header banner should call out the class she's in
        self.assertContains(resp, 'Grade 8 Alpha')

    def test_not_my_student_returns_404(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(
            reverse('teacher:student_detail', args=[self.dave.id])
        )
        self.assertEqual(resp.status_code, 404)

    def test_cross_tenant_student_returns_404(self):
        # Build a student in the other tenant, then try to access them.
        outsider = User.objects.create_user(
            email='out@oes.test', password='p', first_name='Out', last_name='Sider',
            tenant=self.other_tenant, role=self.student_role,
            is_active=True, student_id='SO1',
        )
        StudentProfile.objects.create(student=outsider)
        self.client.force_login(self.teacher)
        resp = self.client.get(
            reverse('teacher:student_detail', args=[outsider.id])
        )
        self.assertEqual(resp.status_code, 404)


# ---------------------------------------------------------------------------
# GRADEBOOK + CSV export
# ---------------------------------------------------------------------------


class GradebookTests(PhaseEFixtureMixin, TestCase):
    def test_renders_matrix_with_real_scores(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse('teacher:gradebook'))
        self.assertEqual(resp.status_code, 200)
        # 3 students × 1 quest matrix
        self.assertContains(resp, 'Alice A')
        self.assertContains(resp, 'Bob B')
        self.assertContains(resp, 'Cara C')
        self.assertContains(resp, 'Photosynthesis Quiz')
        # Alice's 8/10 = 80% should appear
        self.assertContains(resp, '80%')

    def test_class_filter_via_query_string(self):
        # When ?class= matches one of the teacher's classes, the gradebook
        # should switch to that class. We populate c2 with both a student
        # AND a published quest so the matrix branch renders.
        self.client.force_login(self.teacher)
        c2 = self._mk_class(self.teacher, name='Math 8B')
        kira = self._mk_student('kira@pes.test', first='Kira', last='K')
        Enrollment.objects.create(class_obj=c2, student=kira, is_active=True)
        Assignment.objects.create(
            tenant=self.tenant, class_obj=c2, subject=self.subject,
            title='Algebra Quiz', due_date=timezone.now() + timedelta(days=3),
            status=Assignment.STATUS_PUBLISHED, total_marks=10,
            created_by=self.teacher, updated_by=self.teacher,
        )

        resp = self.client.get(reverse('teacher:gradebook') + f'?class={c2.id}')
        self.assertEqual(resp.status_code, 200)
        # Class selected ⇒ Math 8B's roster + its quest column appear,
        # MY default class's roster does NOT.
        self.assertContains(resp, 'Kira K')
        self.assertContains(resp, 'Algebra Quiz')
        self.assertNotContains(resp, 'Photosynthesis Quiz')

    def test_class_filter_with_no_quests_shows_empty_state(self):
        self.client.force_login(self.teacher)
        c2 = self._mk_class(self.teacher, name='No-Quests Class')
        kira = self._mk_student('kira2@pes.test', first='Kira', last='K')
        Enrollment.objects.create(class_obj=c2, student=kira, is_active=True)

        resp = self.client.get(reverse('teacher:gradebook') + f'?class={c2.id}')
        self.assertEqual(resp.status_code, 200)
        # Empty-state copy mentions the class name
        self.assertContains(resp, 'No-Quests Class')
        self.assertContains(resp, 'No published quests')

    def test_unknown_class_falls_back_to_first(self):
        self.client.force_login(self.teacher)
        # Pass a class id that's NOT mine — view should fall back to my first
        resp = self.client.get(
            reverse('teacher:gradebook') + f'?class={self.other_class.id}'
        )
        self.assertEqual(resp.status_code, 200)
        # First class is my_class; should render its students
        self.assertContains(resp, 'Alice A')

    def test_export_csv_for_owning_teacher(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(
            reverse('teacher:gradebook_export', args=[self.my_class.id])
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/csv', resp['Content-Type'])
        self.assertIn('attachment', resp['Content-Disposition'])
        body = resp.content.decode()
        # Header row
        self.assertIn('Student,Email', body)
        self.assertIn('Photosynthesis Quiz', body)
        # Alice's row should carry her 8/10 (80%)
        self.assertIn('Alice A', body)
        self.assertIn('8/10 (80%)', body)
        # Cara has no submissions — empty cell
        self.assertIn('Cara C', body)

    def test_export_csv_other_teachers_class_404(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(
            reverse('teacher:gradebook_export', args=[self.other_class.id])
        )
        self.assertEqual(resp.status_code, 404)
