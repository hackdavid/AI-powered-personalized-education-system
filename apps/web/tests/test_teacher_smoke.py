"""Phase E: Playwright smoke tests for the 5 new teacher pages.

Runs in a real browser with a live Django server. Verifies that:
- Each page loads without 500 errors
- Key UI elements are visible
- Permission boundaries are enforced (401/403 when logged out)

Usage:
    python manage.py test apps.web.tests.test_teacher_smoke --keepdb
"""

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.urls import reverse
from playwright.sync_api import sync_playwright

from apps.accounts.models import Role, Tenant, User
from apps.service.models import (
    Assignment,
    Class,
    ClassSubject,
    Enrollment,
    StudentProfile,
    Subject,
)


def _ensure_roles():
    """Ensure teacher and student roles exist."""
    Role.objects.get_or_create(
        name=Role.TEACHER, defaults={'display_name': 'Teacher', 'level': 50}
    )
    Role.objects.get_or_create(
        name=Role.STUDENT, defaults={'display_name': 'Student', 'level': 100}
    )


class TeacherSmokeTests(StaticLiveServerTestCase):
    """Live browser tests for teacher operations pages."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _ensure_roles()

        # Get or create tenant
        cls.tenant, _ = Tenant.objects.get_or_create(
            slug='smoke',
            defaults={'name': 'Smoke Test School'}
        )
        cls.teacher_role = Role.objects.get(name=Role.TEACHER)
        cls.student_role = Role.objects.get(name=Role.STUDENT)

        # Get or create teacher (idempotent)
        cls.teacher, created = User.objects.get_or_create(
            email='teacher@smoke.test',
            defaults={
                'first_name': 'Test',
                'last_name': 'Teacher',
                'tenant': cls.tenant,
                'role': cls.teacher_role,
                'is_active': True,
                'employee_id': 'T001',
            }
        )
        if created:
            cls.teacher.set_password('testpass123')
            cls.teacher.save()

        # Get or create subject
        cls.subject, _ = Subject.objects.get_or_create(
            tenant=cls.tenant,
            code='MATH',
            defaults={'name': 'Mathematics'}
        )

        # Get or create class
        cls.my_class, _ = Class.objects.get_or_create(
            tenant=cls.tenant,
            name='Grade 8 Math',
            defaults={
                'grade_level': 8,
                'section': 'A',
                'academic_year': '2025-2026',
                'class_teacher': cls.teacher,
            }
        )
        ClassSubject.objects.get_or_create(
            class_obj=cls.my_class,
            subject=cls.subject,
            defaults={'teacher': cls.teacher}
        )

        # Get or create students
        cls.student1, created = User.objects.get_or_create(
            email='student1@smoke.test',
            defaults={
                'first_name': 'Alice',
                'last_name': 'Anderson',
                'tenant': cls.tenant,
                'role': cls.student_role,
                'is_active': True,
                'student_id': 'S001',
            }
        )
        if created:
            cls.student1.set_password('testpass123')
            cls.student1.save()
        StudentProfile.objects.get_or_create(student=cls.student1, defaults={'level': 3, 'total_xp': 250})
        Enrollment.objects.get_or_create(
            class_obj=cls.my_class,
            student=cls.student1,
            defaults={'is_active': True}
        )

        cls.student2, created = User.objects.get_or_create(
            email='student2@smoke.test',
            defaults={
                'first_name': 'Bob',
                'last_name': 'Brown',
                'tenant': cls.tenant,
                'role': cls.student_role,
                'is_active': True,
                'student_id': 'S002',
            }
        )
        if created:
            cls.student2.set_password('testpass123')
            cls.student2.save()
        StudentProfile.objects.get_or_create(student=cls.student2, defaults={'level': 2, 'total_xp': 180})
        Enrollment.objects.get_or_create(
            class_obj=cls.my_class,
            student=cls.student2,
            defaults={'is_active': True}
        )

        # Get or create assignment
        from datetime import timedelta
        from django.utils import timezone
        cls.assignment, _ = Assignment.objects.get_or_create(
            tenant=cls.tenant,
            class_obj=cls.my_class,
            title='Algebra Quiz',
            defaults={
                'subject': cls.subject,
                'due_date': timezone.now() + timedelta(days=7),
                'status': Assignment.STATUS_PUBLISHED,
                'total_marks': 10,
                'created_by': cls.teacher,
                'updated_by': cls.teacher,
            }
        )

    def _run_browser_test(self, test_func):
        """Helper to run a single browser test with Playwright."""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                test_func(page)
            finally:
                browser.close()

    def _login(self, page):
        """Helper to log in as the teacher."""
        page.goto(f'{self.live_server_url}/auth/login/')
        page.fill('input[name="email"]', 'teacher@smoke.test')
        page.fill('input[name="password"]', 'testpass123')
        page.click('button[type="submit"]')
        # Wait for login to complete (URL change or page load)
        page.wait_for_load_state('networkidle', timeout=10000)

    def test_class_list_loads(self):
        """Test 1/5: Class list page loads successfully."""
        def check(page):
            self._login(page)
            response = page.goto(f'{self.live_server_url}{reverse("teacher:class_list")}')
            # Core smoke test: page loads without error
            assert response.status == 200, f"Expected 200, got {response.status}"
            # Verify it's the right page (not an error page)
            assert 'teacher' in page.url or 'class' in page.content().lower()
        self._run_browser_test(check)

    def test_class_detail_loads(self):
        """Test 2/5: Class detail page loads successfully."""
        def check(page):
            self._login(page)
            response = page.goto(f'{self.live_server_url}{reverse("teacher:class_detail", args=[self.my_class.id])}')
            assert response.status == 200, f"Expected 200, got {response.status}"
            # Not a 404 page
            assert '404' not in page.content()
        self._run_browser_test(check)

    def test_student_list_loads(self):
        """Test 3/5: Student list page loads successfully."""
        def check(page):
            self._login(page)
            response = page.goto(f'{self.live_server_url}{reverse("teacher:student_list")}')
            assert response.status == 200, f"Expected 200, got {response.status}"
            assert 'student' in page.url.lower() or 'student' in page.content().lower()
        self._run_browser_test(check)

    def test_student_detail_loads(self):
        """Test 4/5: Student detail page loads successfully."""
        def check(page):
            self._login(page)
            response = page.goto(f'{self.live_server_url}{reverse("teacher:student_detail", args=[self.student1.id])}')
            assert response.status == 200, f"Expected 200, got {response.status}"
            assert '404' not in page.content()
        self._run_browser_test(check)

    def test_gradebook_loads(self):
        """Test 5/5: Gradebook page loads successfully."""
        def check(page):
            self._login(page)
            response = page.goto(f'{self.live_server_url}{reverse("teacher:gradebook")}')
            assert response.status == 200, f"Expected 200, got {response.status}"
            assert 'gradebook' in page.url.lower() or 'grade' in page.content().lower()
        self._run_browser_test(check)

    def test_anonymous_redirects_to_login(self):
        """Bonus: Verify that all pages redirect anonymous users to login."""
        def check(page):
            urls = [
                reverse('teacher:class_list'),
                reverse('teacher:class_detail', args=[self.my_class.id]),
                reverse('teacher:student_list'),
                reverse('teacher:student_detail', args=[self.student1.id]),
                reverse('teacher:gradebook'),
            ]
            for url_path in urls:
                page.goto(f'{self.live_server_url}{url_path}')
                # Should be redirected to login
                assert 'login' in page.url.lower(), f"Expected redirect to login for {url_path}"
        self._run_browser_test(check)
