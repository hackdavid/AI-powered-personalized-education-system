"""
Integration tests for the AI tutor (Phase 2).

The retriever is stubbed everywhere so tests do not depend on ChromaDB or
sentence-transformers. The LLM is also stubbed; we exercise the
`OPENAI_API_KEY` empty path (offline answerer) plus a mock-LLM path so the
'real' branch is also covered without network access.

Coverage:
  * service: stub fallback, persistence of both turns, tenant guard,
    auto-title from first question, last_message_at touch
  * API: tenant isolation (404 across tenants), forbidden for non-students,
    session list scoped by student, message create returns user+assistant,
    auth required
"""

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Role, Tenant, User
from apps.service.models import ChatMessage, Subject, TutoringSession
from apps.service.services.tutoring import TutorService
from apps.service.services.tutoring.retriever import RetrievedChunk
from apps.service.services.tutoring.stub_answerer import STUB_MODEL_NAME


# --------------------------------------------------------------------------- helpers


def _bootstrap_roles():
    for code in (Role.STUDENT, Role.TEACHER, Role.SCHOOL_ADMIN):
        Role.objects.get_or_create(
            name=code,
            defaults={'display_name': code.title(), 'level': 50},
        )


def _create_tenant(slug: str) -> Tenant:
    tenant, _ = Tenant.objects.get_or_create(
        slug=slug,
        defaults={'name': slug.title(), 'is_active': True},
    )
    return tenant


def _create_student(tenant: Tenant, email: str, **extra) -> User:
    role = Role.objects.get(name=Role.STUDENT)
    return User.objects.create_user(
        email=email,
        password='Test@1234',
        first_name=extra.pop('first_name', 'Stu'),
        last_name=extra.pop('last_name', 'Dent'),
        tenant=tenant,
        role=role,
        is_active=True,
        **extra,
    )


def _fake_chunks(n: int = 2):
    """Build deterministic RetrievedChunk objects for service-level tests."""
    out = []
    for i in range(n):
        out.append(RetrievedChunk(
            node_id=f'ch1.s{i+1}.t1',
            document_id=1,
            document_title='Math Grade 8',
            title=f'Topic {i+1}',
            snippet=f'Snippet {i+1} about quadratics.',
            score=0.9 - 0.1 * i,
            page_number=10 + i,
            subject_id=None,
        ))
    return out


# --------------------------------------------------------------------------- service


class TutorServiceTests(TestCase):
    """Unit-ish tests exercising the orchestrator with the retriever stubbed."""

    @classmethod
    def setUpTestData(cls):
        _bootstrap_roles()

    def setUp(self):
        self.tenant = _create_tenant('springfield')
        self.student = _create_student(self.tenant, 'stu@springfield.test', grade_level=8)
        self.session = TutoringSession.objects.create(
            tenant=self.tenant,
            student=self.student,
        )

    # -- offline (no OPENAI_API_KEY) -------------------------------------------------

    @override_settings(OPENAI_API_KEY='')
    @patch('apps.service.services.tutoring.tutor_service.CurriculumRetriever.retrieve')
    def test_stub_answerer_used_when_no_api_key(self, mock_retrieve):
        mock_retrieve.return_value = _fake_chunks(2)

        result = TutorService().answer_question(
            session=self.session,
            student=self.student,
            query='What is a quadratic?',
        )

        self.assertEqual(result.model, STUB_MODEL_NAME)
        self.assertIn('Topic 1', result.assistant_message.content)
        self.assertIn('Topic 2', result.assistant_message.content)
        self.assertIn('offline mode', result.assistant_message.content.lower())
        self.assertEqual(result.assistant_message.model, STUB_MODEL_NAME)
        # 2 messages persisted
        self.assertEqual(self.session.messages.count(), 2)
        # session metadata refreshed
        self.session.refresh_from_db()
        self.assertIsNotNone(self.session.last_message_at)
        self.assertEqual(self.session.title, 'What is a quadratic?')

    # -- "real" LLM branch ----------------------------------------------------------

    @override_settings(OPENAI_API_KEY='sk-test')
    @patch('apps.service.services.tutoring.tutor_service.CurriculumRetriever.retrieve')
    def test_real_llm_branch_uses_llm_service(self, mock_retrieve):
        mock_retrieve.return_value = _fake_chunks(3)

        with patch('clients.llm.LLMService.generate_with_context') as mock_llm:
            mock_llm.return_value = {
                'answer': 'A quadratic [1] is a polynomial of degree 2.',
                'sources': [],
                'model': 'gpt-4-test',
                'timestamp': '2026-04-29T00:00:00Z',
            }
            result = TutorService().answer_question(
                session=self.session,
                student=self.student,
                query='Define a quadratic.',
            )

        mock_llm.assert_called_once()
        self.assertEqual(result.model, 'gpt-4-test')
        self.assertIn('A quadratic', result.assistant_message.content)
        self.assertEqual(len(result.assistant_message.retrieved_chunks), 3)

    # -- LLM failure falls back to stub --------------------------------------------

    @override_settings(OPENAI_API_KEY='sk-test')
    @patch('apps.service.services.tutoring.tutor_service.CurriculumRetriever.retrieve')
    def test_llm_failure_falls_back_to_stub(self, mock_retrieve):
        mock_retrieve.return_value = _fake_chunks(1)

        with patch('clients.llm.LLMService.generate_with_context') as mock_llm:
            mock_llm.side_effect = RuntimeError('upstream error')
            result = TutorService().answer_question(
                session=self.session,
                student=self.student,
                query='Anything?',
            )

        self.assertEqual(result.model, STUB_MODEL_NAME)
        self.assertIn('Topic 1', result.assistant_message.content)

    # -- empty retrieval ----------------------------------------------------------

    @override_settings(OPENAI_API_KEY='sk-test')
    @patch('apps.service.services.tutoring.tutor_service.CurriculumRetriever.retrieve')
    def test_no_sources_does_not_call_llm(self, mock_retrieve):
        mock_retrieve.return_value = []

        with patch('clients.llm.LLMService.generate_with_context') as mock_llm:
            result = TutorService().answer_question(
                session=self.session,
                student=self.student,
                query='?',
            )

        mock_llm.assert_not_called()
        self.assertEqual(result.model, STUB_MODEL_NAME)
        self.assertEqual(result.assistant_message.retrieved_chunks, [])

    # -- guards -----------------------------------------------------------------

    @patch('apps.service.services.tutoring.tutor_service.CurriculumRetriever.retrieve')
    def test_empty_query_rejected(self, mock_retrieve):
        with self.assertRaises(ValueError):
            TutorService().answer_question(
                session=self.session,
                student=self.student,
                query='   ',
            )
        mock_retrieve.assert_not_called()
        self.assertEqual(self.session.messages.count(), 0)

    @patch('apps.service.services.tutoring.tutor_service.CurriculumRetriever.retrieve')
    def test_session_owned_by_other_student_rejected(self, mock_retrieve):
        intruder = _create_student(self.tenant, 'other@springfield.test')

        with self.assertRaises(PermissionError):
            TutorService().answer_question(
                session=self.session,  # owned by self.student
                student=intruder,
                query='Hi',
            )
        mock_retrieve.assert_not_called()
        self.assertEqual(self.session.messages.count(), 0)

    @patch('apps.service.services.tutoring.tutor_service.CurriculumRetriever.retrieve')
    def test_session_in_other_tenant_rejected(self, mock_retrieve):
        other_tenant = _create_tenant('riverside')
        other_student = _create_student(other_tenant, 'stu@riverside.test')

        with self.assertRaises(PermissionError):
            TutorService().answer_question(
                session=self.session,  # springfield
                student=other_student,  # riverside
                query='Hi',
            )
        mock_retrieve.assert_not_called()


# --------------------------------------------------------------------------- API


@override_settings(OPENAI_API_KEY='')
class TutoringAPITests(TestCase):
    """End-to-end checks on the DRF ViewSet, retriever stubbed."""

    @classmethod
    def setUpTestData(cls):
        _bootstrap_roles()

    def setUp(self):
        self.spring = _create_tenant('springfield')
        self.river = _create_tenant('riverside')

        self.spring_subject = Subject.objects.create(
            tenant=self.spring, code='MATH', name='Mathematics', is_active=True,
        )
        self.spring_student = _create_student(self.spring, 'stu@springfield.test', grade_level=8)
        self.river_student = _create_student(self.river, 'stu@riverside.test', grade_level=8)

    def _login(self, user):
        self.client.force_login(user)

    # -- list ----------------------------------------------------------------

    def test_session_list_requires_login(self):
        url = reverse('service_api:tutoring-session-list')
        resp = self.client.get(url)
        # DRF returns 403 when SessionAuthentication has no user
        self.assertIn(resp.status_code, (401, 403))

    def test_session_list_only_returns_own_sessions(self):
        TutoringSession.objects.create(tenant=self.spring, student=self.spring_student, title='mine')
        TutoringSession.objects.create(tenant=self.river, student=self.river_student, title='theirs')

        self._login(self.spring_student)
        url = reverse('service_api:tutoring-session-list')
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body['success'])
        titles = [s['title'] for s in body['data']]
        self.assertEqual(titles, ['mine'])

    def test_session_list_forbidden_for_non_students(self):
        teacher_role = Role.objects.get(name=Role.TEACHER)
        teacher = User.objects.create_user(
            email='t@springfield.test', password='Test@1234',
            first_name='T', last_name='Eacher',
            tenant=self.spring, role=teacher_role, is_active=True,
        )
        self._login(teacher)
        resp = self.client.get(reverse('service_api:tutoring-session-list'))
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(resp.json()['success'])

    # -- create ---------------------------------------------------------------

    def test_create_session(self):
        self._login(self.spring_student)
        url = reverse('service_api:tutoring-session-list')
        resp = self.client.post(url, data={'subject': self.spring_subject.id}, content_type='application/json')

        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertTrue(body['success'])
        self.assertEqual(body['data']['subject'], self.spring_subject.id)
        self.assertEqual(TutoringSession.objects.filter(student=self.spring_student).count(), 1)

    # -- retrieve / cross-tenant guard ----------------------------------------

    def test_cross_tenant_session_returns_404(self):
        # Spring student creates a session
        spring_session = TutoringSession.objects.create(
            tenant=self.spring, student=self.spring_student, title='private',
        )

        # Riverside student tries to read it
        self._login(self.river_student)
        url = reverse('service_api:tutoring-session-detail', args=[spring_session.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    # -- messages action ----------------------------------------------------

    @patch('apps.service.services.tutoring.tutor_service.CurriculumRetriever.retrieve')
    def test_post_message_persists_user_and_assistant(self, mock_retrieve):
        mock_retrieve.return_value = _fake_chunks(2)

        session = TutoringSession.objects.create(
            tenant=self.spring, student=self.spring_student,
        )
        self._login(self.spring_student)
        url = reverse('service_api:tutoring-session-messages', args=[session.id])
        resp = self.client.post(
            url,
            data={'content': 'What is the discriminant?'},
            content_type='application/json',
        )

        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertTrue(body['success'])
        self.assertIn('user_message', body['data'])
        self.assertIn('assistant_message', body['data'])
        self.assertEqual(body['data']['user_message']['role'], 'student')
        self.assertEqual(body['data']['assistant_message']['role'], 'assistant')
        self.assertEqual(body['data']['model'], STUB_MODEL_NAME)

        self.assertEqual(
            ChatMessage.objects.filter(session=session).count(), 2,
            'Both turns must be persisted in one POST.',
        )

    @patch('apps.service.services.tutoring.tutor_service.CurriculumRetriever.retrieve')
    def test_post_message_validation_error(self, mock_retrieve):
        session = TutoringSession.objects.create(
            tenant=self.spring, student=self.spring_student,
        )
        self._login(self.spring_student)
        url = reverse('service_api:tutoring-session-messages', args=[session.id])
        resp = self.client.post(url, data={'content': '   '}, content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])
        mock_retrieve.assert_not_called()

    @patch('apps.service.services.tutoring.tutor_service.CurriculumRetriever.retrieve')
    def test_get_messages_returns_history(self, mock_retrieve):
        session = TutoringSession.objects.create(
            tenant=self.spring, student=self.spring_student,
        )
        ChatMessage.objects.create(session=session, role=ChatMessage.Role.STUDENT, content='hi')
        ChatMessage.objects.create(session=session, role=ChatMessage.Role.ASSISTANT, content='hello', model=STUB_MODEL_NAME)

        self._login(self.spring_student)
        url = reverse('service_api:tutoring-session-messages', args=[session.id])
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body['data']), 2)
        self.assertEqual([m['role'] for m in body['data']], ['student', 'assistant'])
        mock_retrieve.assert_not_called()

    # -- destroy ------------------------------------------------------------

    def test_destroy_archives_session(self):
        session = TutoringSession.objects.create(
            tenant=self.spring, student=self.spring_student,
        )
        self._login(self.spring_student)
        url = reverse('service_api:tutoring-session-detail', args=[session.id])
        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, 200)
        session.refresh_from_db()
        self.assertFalse(session.is_active)
