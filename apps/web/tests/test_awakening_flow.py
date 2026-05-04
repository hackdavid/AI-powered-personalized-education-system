"""Tests for the Awakening onboarding flow."""
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role, Tenant, User
from apps.service.models import OnboardingResult, StudentProfile


def _ensure_roles():
    Role.objects.get_or_create(name=Role.STUDENT, defaults={'display_name': 'Student', 'level': 100})
    Role.objects.get_or_create(name=Role.TEACHER, defaults={'display_name': 'Teacher', 'level': 50})


class AwakeningFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _ensure_roles()
        cls.tenant = Tenant.objects.create(name='A', slug='a')
        cls.student_role = Role.objects.get(name=Role.STUDENT)

    def _student(self, email='s@a.test'):
        u = User.objects.create_user(
            email=email, password='p', first_name='Hunter', last_name='X',
            tenant=self.tenant, role=self.student_role, is_active=True,
            grade_level=8,
        )
        StudentProfile.objects.create(student=u, onboarding_complete=False)
        return u

    def test_welcome_requires_login(self):
        resp = self.client.get(reverse('student:awakening'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/auth/login', resp.url)

    def test_welcome_renders_for_student(self):
        self.client.force_login(self._student())
        resp = self.client.get(reverse('student:awakening'))
        self.assertEqual(resp.status_code, 200)

    def test_cannot_skip_to_later_step(self):
        self.client.force_login(self._student())
        resp = self.client.get(reverse('student:awakening_goal'), follow=False)
        # Should redirect back to the earliest allowed step
        self.assertEqual(resp.status_code, 302)

    def test_identity_post_advances(self):
        u = self._student()
        self.client.force_login(u)
        resp = self.client.post(reverse('student:awakening_identity'), {
            'hunter_title': 'scholar',
            'interest_tags': ['Math', 'Science'],
        })
        self.assertEqual(resp.status_code, 302)
        result = OnboardingResult.objects.get(student=u)
        self.assertEqual(result.step_1_identity.get('hunter_title'), 'scholar')
        self.assertGreaterEqual(result.current_step, 3)

    def test_full_flow_marks_complete(self):
        u = self._student()
        self.client.force_login(u)

        # Step 1: identity
        self.client.post(reverse('student:awakening_identity'), {
            'hunter_title': 'explorer', 'interest_tags': ['Math'],
        })
        # Step 2: learning style
        self.client.post(reverse('student:awakening_learning_style'), {
            'q1': 'v', 'q2': 'v', 'q3': 'r', 'q4': 'k',
        })
        # Step 3: goal
        self.client.post(reverse('student:awakening_goal'), {
            'goal_template': 'Pass this term confidently',
            'goal_title': 'Pass all my exams',
            'goal_description': 'Focus on weak subjects.',
        })
        # Step 4: aptitude — skip if no questions generated (test env may have no nodes)
        result = OnboardingResult.objects.get(student=u)
        for _ in range(10):
            result.refresh_from_db()
            if result.current_step >= 6:
                break
            resp = self.client.post(reverse('student:awakening_aptitude'), {
                'selected': '',
            })
            if resp.status_code != 302:
                break
        # Step 5: complete
        resp = self.client.get(reverse('student:awakening_complete'))
        self.assertEqual(resp.status_code, 200)

        u.refresh_from_db()
        profile = u.profile
        self.assertTrue(profile.onboarding_complete)
