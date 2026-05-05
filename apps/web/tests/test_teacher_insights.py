"""Phase F: Tests for Teacher Insights dashboard.

Tests all three insight components:
1. Struggling students queue (auto-flagged based on risk factors)
2. Top performers spotlight (leaderboard)
3. Mastery heatmap (subject × student grid)
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
    Question,
    StudentAssignment,
    StudentProfile,
    Subject,
)


def _ensure_roles():
    Role.objects.get_or_create(
        name=Role.TEACHER, defaults={'display_name': 'Teacher', 'level': 50})
    Role.objects.get_or_create(
        name=Role.STUDENT, defaults={'display_name': 'Student', 'level': 100})


class InsightsFixtureMixin:
    """Shared setup: teacher, class, students with varied performance profiles."""

    @classmethod
    def setUpTestData(cls):
        _ensure_roles()
        cls.tenant = Tenant.objects.create(name='Insights School', slug='ins')
        cls.teacher_role = Role.objects.get(name=Role.TEACHER)
        cls.student_role = Role.objects.get(name=Role.STUDENT)

        # Teacher + class
        cls.teacher = cls._mk_teacher('teacher@ins.test')
        cls.subject1 = Subject.objects.create(tenant=cls.tenant, code='MATH', name='Math')
        cls.subject2 = Subject.objects.create(tenant=cls.tenant, code='SCI', name='Science')
        cls.my_class = cls._mk_class(cls.teacher, 'Grade 10A')

        # Create diverse student profiles for testing insights

        # Student 1: Struggling (low mastery, inactive, broken streak)
        cls.struggling_student = cls._mk_student('struggling@ins.test', first='Struggling', last='Student')
        Enrollment.objects.create(class_obj=cls.my_class, student=cls.struggling_student, is_active=True)
        StudentProfile.objects.create(
            student=cls.struggling_student,
            level=2,
            total_xp=50,
            streak_days=0,  # Broken streak
            last_active_date=timezone.now().date() - timedelta(days=5),  # Inactive 5 days
            mastery_per_subject={str(cls.subject1.id): 30, str(cls.subject2.id): 25},  # Low mastery
        )

        # Student 2: Top performer (high XP, streak, mastery)
        cls.top_student = cls._mk_student('top@ins.test', first='Top', last='Performer')
        Enrollment.objects.create(class_obj=cls.my_class, student=cls.top_student, is_active=True)
        StudentProfile.objects.create(
            student=cls.top_student,
            level=10,
            total_xp=5000,
            streak_days=30,
            last_active_date=timezone.now().date(),
            mastery_per_subject={str(cls.subject1.id): 95, str(cls.subject2.id): 88},
            rank='S',
        )

        # Student 3: Average student
        cls.avg_student = cls._mk_student('avg@ins.test', first='Average', last='Student')
        Enrollment.objects.create(class_obj=cls.my_class, student=cls.avg_student, is_active=True)
        StudentProfile.objects.create(
            student=cls.avg_student,
            level=5,
            total_xp=800,
            streak_days=7,
            last_active_date=timezone.now().date() - timedelta(days=1),
            mastery_per_subject={str(cls.subject1.id): 65, str(cls.subject2.id): 70},
            rank='C',
        )

        # Student 4: Another struggling (low mastery, low streak)
        cls.struggling_student2 = cls._mk_student('struggling2@ins.test', first='Also', last='Struggling')
        Enrollment.objects.create(class_obj=cls.my_class, student=cls.struggling_student2, is_active=True)
        StudentProfile.objects.create(
            student=cls.struggling_student2,
            level=3,
            total_xp=120,
            streak_days=1,
            last_active_date=timezone.now().date() - timedelta(days=4),
            mastery_per_subject={str(cls.subject1.id): 35, str(cls.subject2.id): 38},
        )

        # Create some graded assignments for quest score calculations
        now = timezone.now()
        assignment = Assignment.objects.create(
            tenant=cls.tenant,
            class_obj=cls.my_class,
            subject=cls.subject1,
            title='Test Quest',
            due_date=now + timedelta(days=1),
            status='published',
            total_marks=100,
            created_by=cls.teacher,
            updated_by=cls.teacher,
        )

        # Top student: high score
        StudentAssignment.objects.create(
            assignment=assignment,
            student=cls.top_student,
            status='graded',
            score=95,
            max_score=100,
        )

        # Struggling student: low score
        StudentAssignment.objects.create(
            assignment=assignment,
            student=cls.struggling_student,
            status='graded',
            score=40,
            max_score=100,
        )

    @classmethod
    def _mk_teacher(cls, email):
        return User.objects.create_user(
            email=email, password='p', first_name='T', last_name='X',
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
    def _mk_class(cls, teacher, name):
        section = chr(65 + Class.objects.count() % 26)
        c = Class.objects.create(
            tenant=cls.tenant, name=name,
            grade_level=10 + (Class.objects.count() % 3), section=section,
            academic_year='2025-2026',
            class_teacher=teacher,
        )
        ClassSubject.objects.create(class_obj=c, subject=cls.subject1, teacher=teacher)
        return c


# ---------------------------------------------------------------------------
# Insights View Tests
# ---------------------------------------------------------------------------


class InsightsViewTests(InsightsFixtureMixin, TestCase):
    def test_anonymous_redirects_to_login(self):
        resp = self.client.get(reverse('teacher:insights'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('login', resp.url)

    def test_teacher_sees_insights_page(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse('teacher:insights'))
        self.assertEqual(resp.status_code, 200)
        # Should have all three sections
        self.assertContains(resp, 'Struggling Students')
        self.assertContains(resp, 'Top Performers')
        self.assertContains(resp, 'Mastery Heatmap')

    def test_class_selector_shows_all_teacher_classes(self):
        # Create a second class
        class2 = self._mk_class(self.teacher, 'Grade 11B')
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse('teacher:insights'))
        self.assertContains(resp, 'Grade 10A')
        self.assertContains(resp, 'Grade 11B')

    def test_class_filter_works(self):
        class2 = self._mk_class(self.teacher, 'Grade 11B')
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse('teacher:insights') + f'?class={class2.id}')
        self.assertEqual(resp.status_code, 200)
        # Selected class name should appear in context
        self.assertEqual(resp.context['selected_class'].id, class2.id)


# ---------------------------------------------------------------------------
# Struggling Students Tests
# ---------------------------------------------------------------------------


class StrugglingStudentsTests(InsightsFixtureMixin, TestCase):
    def test_identifies_struggling_students(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse('teacher:insights'))

        # Should flag both struggling students
        struggling = resp.context['struggling_students']
        self.assertGreaterEqual(len(struggling), 2)

        # Check that struggling students are in the list
        struggling_ids = [s['student'].id for s in struggling]
        self.assertIn(self.struggling_student.id, struggling_ids)
        self.assertIn(self.struggling_student2.id, struggling_ids)

        # Average student should NOT be flagged
        self.assertNotIn(self.avg_student.id, struggling_ids)

        # Top student should NOT be flagged
        self.assertNotIn(self.top_student.id, struggling_ids)

    def test_risk_factors_displayed(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse('teacher:insights'))

        # Should show risk factors like "Low mastery", "Inactive X days", etc.
        self.assertContains(resp, 'Low mastery')
        self.assertContains(resp, 'Inactive')
        self.assertContains(resp, 'Streak')

    def test_risk_score_calculated(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse('teacher:insights'))

        struggling = resp.context['struggling_students']
        for item in struggling:
            # Risk score should be positive
            self.assertGreater(item['risk_score'], 0)
            # Should have at least 2 risk factors
            self.assertGreaterEqual(len(item['risk_factors']), 2)

    def test_sorted_by_risk_score(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse('teacher:insights'))

        struggling = resp.context['struggling_students']
        if len(struggling) > 1:
            # Should be sorted descending by risk score
            for i in range(len(struggling) - 1):
                self.assertGreaterEqual(
                    struggling[i]['risk_score'],
                    struggling[i + 1]['risk_score']
                )

    def test_no_struggling_students_shows_empty_state(self):
        # Create a new class with only high-performing students
        class2 = self._mk_class(self.teacher, 'All Stars')
        top_student2 = self._mk_student('top2@ins.test', first='Another', last='TopStudent')
        Enrollment.objects.create(class_obj=class2, student=top_student2, is_active=True)
        StudentProfile.objects.create(
            student=top_student2,
            level=10,
            total_xp=6000,
            streak_days=50,
            last_active_date=timezone.now().date(),
            mastery_per_subject={str(self.subject1.id): 100, str(self.subject2.id): 98},
        )

        self.client.force_login(self.teacher)
        resp = self.client.get(reverse('teacher:insights') + f'?class={class2.id}')

        # Should show empty state
        self.assertContains(resp, 'No struggling students detected')


# ---------------------------------------------------------------------------
# Top Performers Tests
# ---------------------------------------------------------------------------


class TopPerformersTests(InsightsFixtureMixin, TestCase):
    def test_shows_top_performers(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse('teacher:insights'))

        performers = resp.context['top_performers']
        self.assertGreater(len(performers), 0)

        # Top student should be #1
        self.assertEqual(performers[0]['student'].id, self.top_student.id)

    def test_rank_by_xp(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse('teacher:insights') + '?metric=xp')

        performers = resp.context['top_performers']
        # Should be sorted by total_xp descending
        for i in range(len(performers) - 1):
            self.assertGreaterEqual(
                performers[i]['total_xp'],
                performers[i + 1]['total_xp']
            )

    def test_rank_by_mastery(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse('teacher:insights') + '?metric=mastery')

        performers = resp.context['top_performers']
        # Top performer should have highest mastery
        self.assertEqual(performers[0]['student'].id, self.top_student.id)
        self.assertGreater(performers[0]['avg_mastery'], 80)

    def test_rank_by_streak(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse('teacher:insights') + '?metric=streak')

        performers = resp.context['top_performers']
        # Should be sorted by streak_days descending
        for i in range(len(performers) - 1):
            self.assertGreaterEqual(
                performers[i]['streak_days'],
                performers[i + 1]['streak_days']
            )

    def test_rank_by_quest_score(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse('teacher:insights') + '?metric=quest_score')

        performers = resp.context['top_performers']
        # Top student should have highest quest score
        top_performer = performers[0]
        self.assertEqual(top_performer['student'].id, self.top_student.id)

    def test_displays_performer_stats(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse('teacher:insights'))

        # Should show XP, mastery, streak
        self.assertContains(resp, '5000')  # Top student's XP
        self.assertContains(resp, '30')    # Top student's streak


# ---------------------------------------------------------------------------
# Mastery Heatmap Tests
# ---------------------------------------------------------------------------


class MasteryHeatmapTests(InsightsFixtureMixin, TestCase):
    def test_heatmap_shows_all_students(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse('teacher:insights'))

        students = resp.context['heatmap_students']
        self.assertEqual(len(students), 4)  # 4 students enrolled

        student_names = [s['name'] for s in students]
        self.assertIn('Top Performer', student_names)
        self.assertIn('Struggling Student', student_names)
        self.assertIn('Average Student', student_names)

    def test_heatmap_shows_all_subjects(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse('teacher:insights'))

        subjects = resp.context['heatmap_subjects']
        self.assertEqual(len(subjects), 2)  # Math and Science

        subject_names = [s.name for s in subjects]
        self.assertIn('Math', subject_names)
        self.assertIn('Science', subject_names)

    def test_heatmap_matrix_has_correct_values(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse('teacher:insights'))

        matrix = resp.context['heatmap_matrix']

        # Top student should have high mastery (95% Math, 88% Science)
        top_math = matrix.get((self.top_student.id, self.subject1.id))
        top_sci = matrix.get((self.top_student.id, self.subject2.id))
        self.assertEqual(top_math, 95)
        self.assertEqual(top_sci, 88)

        # Struggling student should have low mastery (30% Math, 25% Science)
        struggling_math = matrix.get((self.struggling_student.id, self.subject1.id))
        struggling_sci = matrix.get((self.struggling_student.id, self.subject2.id))
        self.assertEqual(struggling_math, 30)
        self.assertEqual(struggling_sci, 25)

    def test_heatmap_calculates_class_averages(self):
        self.client.force_login(self.teacher)
        resp = self.client.get(reverse('teacher:insights'))

        averages = resp.context['heatmap_averages']

        # Should have averages for both subjects
        self.assertIn(self.subject1.id, averages)
        self.assertIn(self.subject2.id, averages)

        # Math average: (95 + 30 + 65 + 35) / 4 = 56.25 ≈ 56
        math_avg = averages[self.subject1.id]
        self.assertIsNotNone(math_avg)
        self.assertGreater(math_avg, 50)
        self.assertLess(math_avg, 60)

    def test_heatmap_handles_missing_mastery_data(self):
        # Create a student with NO mastery data
        no_data_student = self._mk_student('nodata@ins.test', first='No', last='Data')
        Enrollment.objects.create(class_obj=self.my_class, student=no_data_student, is_active=True)
        StudentProfile.objects.create(
            student=no_data_student,
            level=1,
            total_xp=10,
            mastery_per_subject={},  # Empty
        )

        self.client.force_login(self.teacher)
        resp = self.client.get(reverse('teacher:insights'))

        matrix = resp.context['heatmap_matrix']
        # Should not have entries for this student (gracefully handled)
        no_data_math = matrix.get((no_data_student.id, self.subject1.id))
        self.assertIsNone(no_data_math)


# ---------------------------------------------------------------------------
# Permission Tests
# ---------------------------------------------------------------------------


class InsightsPermissionTests(InsightsFixtureMixin, TestCase):
    def test_other_teacher_sees_only_their_classes(self):
        # Create another teacher with their own class
        other_teacher = self._mk_teacher('other@ins.test')
        other_class = self._mk_class(other_teacher, 'Other Class')

        self.client.force_login(other_teacher)
        resp = self.client.get(reverse('teacher:insights'))

        # Should see their own class
        self.assertEqual(resp.context['selected_class'].id, other_class.id)

        # Should NOT see the first teacher's students
        students = resp.context['heatmap_students']
        student_names = [s['name'] for s in students]
        self.assertNotIn('Top Performer', student_names)
        self.assertNotIn('Struggling Student', student_names)
