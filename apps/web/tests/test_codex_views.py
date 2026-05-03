"""Tests for the student-facing Codex curriculum atlas."""

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role, Tenant, User
from apps.service.models import ContentNode, Document, StudentProfile, Subject


def _ensure_roles():
    Role.objects.get_or_create(
        name=Role.STUDENT, defaults={'display_name': 'Student', 'level': 100})


class CodexViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        _ensure_roles()
        cls.tenant = Tenant.objects.create(name='Codex Tenant', slug='codex')
        cls.other_tenant = Tenant.objects.create(name='Other', slug='other')
        cls.student_role = Role.objects.get(name=Role.STUDENT)

        cls.subject = Subject.objects.create(
            tenant=cls.tenant, code='MATH', name='Mathematics',
            description='Number, algebra, geometry.',
        )
        cls.other_subject = Subject.objects.create(
            tenant=cls.other_tenant, code='SCI', name='Science',
        )

        cls.doc = Document.objects.create(
            tenant=cls.tenant, title='Math Grade 8', source_type='synthetic',
        )
        cls.chapter = ContentNode.objects.create(
            tenant=cls.tenant, subject=cls.subject, document=cls.doc,
            node_id='ch1', node_type='chapter',
            title='Chapter 1: Numbers', content='# Chapter 1\n\nIntro paragraph.',
            content_plain='Chapter 1 Intro paragraph.',
            position=1,
        )
        cls.section = ContentNode.objects.create(
            tenant=cls.tenant, subject=cls.subject, document=cls.doc,
            parent=cls.chapter, node_id='ch1.s1', node_type='section',
            title='Integers', content='**Integers** are whole numbers.',
            content_plain='Integers are whole numbers.',
            position=1,
        )
        cls.topic = ContentNode.objects.create(
            tenant=cls.tenant, subject=cls.subject, document=cls.doc,
            parent=cls.section, node_id='ch1.s1.t1', node_type='topic',
            title='Addition', content='Adding two integers...',
            content_plain='Adding two integers...',
            position=1,
        )
        # Cross-tenant node — the student should NEVER see this
        cls.other_doc = Document.objects.create(
            tenant=cls.other_tenant, title='Other', source_type='synthetic',
        )
        cls.other_chapter = ContentNode.objects.create(
            tenant=cls.other_tenant, subject=cls.other_subject, document=cls.other_doc,
            node_id='ch1', node_type='chapter', title='Other Tenant Chapter',
            content='Hidden.', content_plain='Hidden.', position=1,
        )

    def _student(self, email='c@codex.test'):
        u = User.objects.create_user(
            email=email, password='p', first_name='C', last_name='X',
            tenant=self.tenant, role=self.student_role,
            is_active=True, grade_level=8,
        )
        StudentProfile.objects.create(student=u, onboarding_complete=True)
        return u

    def test_list_requires_login(self):
        resp = self.client.get(reverse('student:codex_list'))
        self.assertEqual(resp.status_code, 302)

    def test_list_shows_tenant_subjects(self):
        u = self._student()
        self.client.force_login(u)
        resp = self.client.get(reverse('student:codex_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Mathematics')
        self.assertNotContains(resp, 'Other Tenant Chapter')

    def test_subject_view_lists_chapters_and_sections(self):
        u = self._student()
        self.client.force_login(u)
        resp = self.client.get(reverse('student:codex_subject', args=[self.subject.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Chapter 1: Numbers')
        self.assertContains(resp, 'Integers')

    def test_subject_view_404s_for_other_tenants_subject(self):
        u = self._student()
        self.client.force_login(u)
        resp = self.client.get(reverse('student:codex_subject', args=[self.other_subject.id]))
        self.assertEqual(resp.status_code, 404)

    def test_node_view_renders_with_breadcrumb(self):
        u = self._student()
        self.client.force_login(u)
        resp = self.client.get(reverse('student:codex_node', args=[self.topic.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Addition')
        # breadcrumb should include parent titles
        self.assertContains(resp, 'Chapter 1: Numbers')
        self.assertContains(resp, 'Integers')

    def test_node_view_shows_children_when_present(self):
        u = self._student()
        self.client.force_login(u)
        resp = self.client.get(reverse('student:codex_node', args=[self.section.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Addition')  # section's child

    def test_node_view_404s_across_tenants(self):
        u = self._student()
        self.client.force_login(u)
        resp = self.client.get(reverse('student:codex_node', args=[self.other_chapter.id]))
        self.assertEqual(resp.status_code, 404)

    def test_node_view_exposes_hunt_and_chat_ctas(self):
        u = self._student()
        self.client.force_login(u)
        resp = self.client.get(reverse('student:codex_node', args=[self.topic.id]))
        self.assertContains(resp, 'Ask the System Advisor')
        self.assertContains(resp, 'Start a Hunt')
