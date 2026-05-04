"""Tests for OnboardingRequiredMiddleware."""

from django.test import TestCase

from apps.accounts.models import Role, Tenant, User
from apps.service.models import StudentProfile


def _ensure_roles():
    Role.objects.get_or_create(
        name=Role.STUDENT,
        defaults={'display_name': 'Student', 'level': 100},
    )
    Role.objects.get_or_create(
        name=Role.TEACHER,
        defaults={'display_name': 'Teacher', 'level': 50},
    )


class OnboardingWallTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _ensure_roles()
        cls.tenant = Tenant.objects.create(name='Wall Test', slug='wall')
        cls.student_role = Role.objects.get(name=Role.STUDENT)
        cls.teacher_role = Role.objects.get(name=Role.TEACHER)

    def _student(self, email, onboarded=False):
        u = User.objects.create_user(
            email=email, password='p', first_name='S', last_name='T',
            tenant=self.tenant, role=self.student_role,
            is_active=True, grade_level=8,
        )
        StudentProfile.objects.create(student=u, onboarding_complete=onboarded)
        return u

    def test_incomplete_student_is_walled_from_dashboard(self):
        u = self._student('inc@wall.test', onboarded=False)
        self.client.force_login(u)
        resp = self.client.get('/dashboard/', follow=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/student/awakening', resp.url)

    def test_incomplete_student_is_walled_from_chat(self):
        u = self._student('chat@wall.test', onboarded=False)
        self.client.force_login(u)
        resp = self.client.get('/student/chat/', follow=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/student/awakening', resp.url)

    def test_complete_student_is_not_walled(self):
        u = self._student('done@wall.test', onboarded=True)
        self.client.force_login(u)
        resp = self.client.get('/student/chat/', follow=False)
        if resp.status_code == 302:
            self.assertNotIn('/student/awakening', resp.url)

    def test_awakening_path_is_allowed_even_if_incomplete(self):
        u = self._student('aw@wall.test', onboarded=False)
        self.client.force_login(u)
        resp = self.client.get('/student/awakening/')
        # Must not infinite-loop; either 200/404 or a redirect that's NOT to awakening.
        if resp.status_code == 302:
            self.assertNotIn('/student/awakening', resp.url)

    def test_shell_preview_is_allowed_even_if_incomplete(self):
        u = self._student('prev@wall.test', onboarded=False)
        self.client.force_login(u)
        resp = self.client.get('/student/shell-preview/')
        self.assertEqual(resp.status_code, 200)

    def test_logout_is_allowed_even_if_incomplete(self):
        u = self._student('out@wall.test', onboarded=False)
        self.client.force_login(u)
        resp = self.client.get('/auth/logout/')
        if resp.status_code == 302:
            self.assertNotIn('/student/awakening', resp.url)

    def test_teacher_is_never_walled(self):
        t = User.objects.create_user(
            email='t@wall.test', password='p', first_name='T', last_name='T',
            tenant=self.tenant, role=self.teacher_role, is_active=True,
        )
        self.client.force_login(t)
        resp = self.client.get('/dashboard/', follow=False)
        if resp.status_code == 302:
            self.assertNotIn('/student/awakening', resp.url)

    def test_anonymous_is_not_walled(self):
        # Redirect should go to login, not to awakening.
        resp = self.client.get('/dashboard/', follow=False)
        if resp.status_code == 302:
            self.assertNotIn('/student/awakening', resp.url)
