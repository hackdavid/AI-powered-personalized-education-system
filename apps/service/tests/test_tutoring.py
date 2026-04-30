"""
Integration tests for the AI tutor.

The retriever, router, and LLM are all stubbed so tests don't need pgvector,
sentence-transformers, or network access. We exercise:

  * service: stub fallback, persistence of both turns, routing metadata,
    tenant guard, auto-title, last_message_at touch, subject_id propagation
    through the retriever
  * router: single-LLM-call branch returns expected Routing, fallback to
    embedding ranking when LLM is misconfigured, intent short-circuit
  * streaming API: SSE endpoint emits the expected event sequence and
    persists the same messages as the blocking one
  * API: tenant isolation, forbidden for non-students, session list scoped,
    message create returns routing + sources, create no longer accepts subject
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Role, Tenant, User
from apps.service.models import ChatMessage, Subject, TutoringSession
from apps.service.services.tutoring import (
    CurriculumRetriever,
    QueryRouter,
    Routing,
    TutorService,
    TutorUnavailable,
)
from apps.service.services.tutoring.catalog import Chapter, SubjectCatalog
from apps.service.services.tutoring.retriever import RetrievedChunk


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
            node_id=f'ch1.s{i + 1}.t1',
            document_id=1,
            document_title='Math Grade 8',
            title=f'Topic {i + 1}',
            snippet=f'Snippet {i + 1} about quadratics.',
            score=0.9 - 0.1 * i,
            page_number=10 + i,
            subject_id=None,
            subject_name='Mathematics',
        ))
    return out


def _math_routing(subject_id: int = 1, topic: str = 'Polynomials') -> Routing:
    return Routing(
        subject_ids=[subject_id],
        subject_names=['Mathematics'],
        topic_titles=[topic],
        refined_query='Explain quadratic equations standard form.',
        intent='concept_explanation',
        needs_retrieval=True,
        confidence=0.88,
        candidate_subject_ids=[subject_id],
        source='llm',
    )


# --------------------------------------------------------------------------- TutorService


@override_settings(OPENAI_API_KEY='')
class TutorServiceUnconfiguredTests(TestCase):
    """When no LLM is configured we refuse the request — no demo answers."""

    @classmethod
    def setUpTestData(cls):
        _bootstrap_roles()

    def setUp(self):
        self.tenant = _create_tenant('springfield')
        self.student = _create_student(self.tenant, 'stu@springfield.test', grade_level=8)
        self.session = TutoringSession.objects.create(tenant=self.tenant, student=self.student)

    @patch('apps.service.services.tutoring.tutor_service.CurriculumRetriever.retrieve')
    @patch('apps.service.services.tutoring.tutor_service.QueryRouter.route')
    def test_missing_api_key_raises_tutor_unavailable(self, mock_route, mock_retrieve):
        """The tutor must NOT emit 'offline mode' or demo content.

        With no OPENAI_API_KEY, we raise TutorUnavailable before any
        retrieval / LLM call happens. The API layer turns this into a
        clean 503 with a neutral 'temporarily unavailable' message.
        """
        with self.assertRaises(TutorUnavailable):
            TutorService().answer_question(
                session=self.session,
                student=self.student,
                query='What is a quadratic?',
            )

        # No DB writes should have happened — not even the student turn.
        self.assertEqual(self.session.messages.count(), 0)
        mock_route.assert_not_called()
        mock_retrieve.assert_not_called()


@override_settings(OPENAI_API_KEY='sk-test')
class TutorServiceLLMTests(TestCase):
    """Behaviour when the LLM answerer branch is active."""

    @classmethod
    def setUpTestData(cls):
        _bootstrap_roles()

    def setUp(self):
        self.tenant = _create_tenant('springfield')
        self.student = _create_student(self.tenant, 'stu@springfield.test', grade_level=8)
        self.session = TutoringSession.objects.create(tenant=self.tenant, student=self.student)

    @patch('apps.service.services.tutoring.tutor_service.CurriculumRetriever.retrieve')
    @patch('apps.service.services.tutoring.tutor_service.QueryRouter.route')
    def test_real_llm_branch_uses_llm_service(self, mock_route, mock_retrieve):
        mock_route.return_value = _math_routing()
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
        # Retriever was called with subject_ids from routing.
        retrieve_kwargs = mock_retrieve.call_args.kwargs
        self.assertEqual(retrieve_kwargs.get('subject_ids'), [1])
        self.assertEqual(retrieve_kwargs.get('topic_titles'), ['Polynomials'])

        self.assertEqual(result.model, 'gpt-4-test')
        self.assertIn('A quadratic', result.assistant_message.content)
        self.assertEqual(len(result.assistant_message.retrieved_chunks), 3)

    @patch('apps.service.services.tutoring.tutor_service.CurriculumRetriever.retrieve')
    @patch('apps.service.services.tutoring.tutor_service.QueryRouter.route')
    def test_llm_failure_propagates_not_swallowed(self, mock_route, mock_retrieve):
        """LLM errors must bubble up — no fake "offline" content leaks out."""
        mock_route.return_value = _math_routing()
        mock_retrieve.return_value = _fake_chunks(1)

        with patch('clients.llm.LLMService.generate_with_context') as mock_llm:
            mock_llm.side_effect = RuntimeError('upstream error')
            with self.assertRaises(RuntimeError):
                TutorService().answer_question(
                    session=self.session,
                    student=self.student,
                    query='Anything?',
                )

    @patch('apps.service.services.tutoring.tutor_service.CurriculumRetriever.retrieve')
    @patch('apps.service.services.tutoring.tutor_service.QueryRouter.route')
    def test_no_sources_still_calls_llm_with_no_context_prompt(self, mock_route, mock_retrieve):
        """When retrieval returns zero hits we still go to the LLM — no stub.

        The LLM answers from general knowledge using the no-context prompt
        (no [N] citations), via plain `generate()` rather than RAG. The
        title-refinement path also uses `generate()` under the hood, so we
        expect two calls and assert the *first* one is the no-context answer.
        """
        mock_route.return_value = _math_routing()
        mock_retrieve.return_value = []

        with patch('clients.llm.LLMService.generate') as mock_generate, \
             patch('clients.llm.LLMService.generate_with_context') as mock_rag:
            # Return a different string per call so we can tell them apart.
            mock_generate.side_effect = [
                'A quadratic is a polynomial of degree 2.',   # no-context answer
                'Quadratic Definition',                        # title refinement
            ]
            result = TutorService().answer_question(
                session=self.session,
                student=self.student,
                query='What is a quadratic?',
            )

        mock_rag.assert_not_called()
        # Two calls: the no-context answer + the title refinement.
        self.assertEqual(mock_generate.call_count, 2)

        # First call is the no-context answer — ensure we told the LLM not to cite.
        first_system = mock_generate.call_args_list[0].kwargs.get('system') or ''
        self.assertIn('could not find any matching curriculum', first_system)
        self.assertIn('Do NOT use [N] citations', first_system)

        # Second call is the title refinement.
        second_system = mock_generate.call_args_list[1].kwargs.get('system') or ''
        self.assertIn('conversation title', second_system.lower())

        self.assertIn('polynomial', result.assistant_message.content)
        self.assertEqual(result.assistant_message.retrieved_chunks, [])
        # No demo / offline phrasing leaked through.
        self.assertNotIn('offline mode', result.assistant_message.content.lower())
        self.assertNotIn('no llm configured', result.assistant_message.content.lower())

    @patch('clients.llm.LLMService.generate')
    @patch('clients.llm.LLMService.generate_with_context')
    @patch('apps.service.services.tutoring.tutor_service.CurriculumRetriever.retrieve')
    @patch('apps.service.services.tutoring.tutor_service.QueryRouter.route')
    def test_first_round_refines_session_title_with_llm(
        self, mock_route, mock_retrieve, mock_rag, mock_generate,
    ):
        """After the first Q&A round we replace the truncated-question title
        with a concise LLM-generated one, and surface it in the response.
        """
        mock_route.return_value = _math_routing()
        mock_retrieve.return_value = _fake_chunks(2)
        mock_rag.return_value = {
            'answer': 'The discriminant is $b^2 - 4ac$ [1].',
            'sources': [],
            'model': 'gpt-4o-mini',
            'timestamp': '2026-04-30T00:00:00Z',
        }
        # `generate` is used for the title refinement call.
        mock_generate.return_value = '  "Quadratic Discriminant Explained"  '

        result = TutorService().answer_question(
            session=self.session,
            student=self.student,
            query='What is the discriminant of a quadratic?',
        )

        # `generate` was invoked exactly once (the title call). `generate_with_context`
        # handled the answer.
        mock_generate.assert_called_once()
        title_system = mock_generate.call_args.kwargs.get('system') or ''
        self.assertIn('conversation title', title_system.lower())

        # Title was cleaned (quotes / trailing punctuation stripped) and
        # persisted to the session row.
        self.session.refresh_from_db()
        self.assertEqual(self.session.title, 'Quadratic Discriminant Explained')
        self.assertEqual(result.session_title, 'Quadratic Discriminant Explained')
        self.assertTrue(result.title_changed)

    @patch('clients.llm.LLMService.generate')
    @patch('clients.llm.LLMService.generate_with_context')
    @patch('apps.service.services.tutoring.tutor_service.CurriculumRetriever.retrieve')
    @patch('apps.service.services.tutoring.tutor_service.QueryRouter.route')
    def test_title_refinement_only_runs_on_first_round(
        self, mock_route, mock_retrieve, mock_rag, mock_generate,
    ):
        """Follow-up turns must not overwrite a title the student may have edited."""
        mock_route.return_value = _math_routing()
        mock_retrieve.return_value = _fake_chunks(1)
        mock_rag.return_value = {
            'answer': 'Second answer.', 'sources': [],
            'model': 'gpt-4o-mini', 'timestamp': '2026-04-30T00:00:00Z',
        }

        # Pre-seed two messages so the new round becomes turn 3 + 4.
        ChatMessage.objects.create(
            session=self.session, role=ChatMessage.Role.STUDENT, content='earlier q',
        )
        ChatMessage.objects.create(
            session=self.session, role=ChatMessage.Role.ASSISTANT,
            content='earlier a', model='gpt-4o-mini',
        )
        self.session.title = 'User Edited Title'
        self.session.save(update_fields=['title'])

        result = TutorService().answer_question(
            session=self.session,
            student=self.student,
            query='Follow-up question?',
        )

        mock_generate.assert_not_called()
        self.session.refresh_from_db()
        self.assertEqual(self.session.title, 'User Edited Title')
        self.assertFalse(result.title_changed)

    @patch('clients.llm.LLMService.generate')
    @patch('clients.llm.LLMService.generate_with_context')
    @patch('apps.service.services.tutoring.tutor_service.CurriculumRetriever.retrieve')
    @patch('apps.service.services.tutoring.tutor_service.QueryRouter.route')
    def test_title_refinement_swallows_llm_errors(
        self, mock_route, mock_retrieve, mock_rag, mock_generate,
    ):
        """Title call failing must NOT break the main Q&A round."""
        mock_route.return_value = _math_routing()
        mock_retrieve.return_value = _fake_chunks(1)
        mock_rag.return_value = {
            'answer': 'An answer.', 'sources': [],
            'model': 'gpt-4o-mini', 'timestamp': '2026-04-30T00:00:00Z',
        }
        mock_generate.side_effect = RuntimeError('title endpoint 503')

        result = TutorService().answer_question(
            session=self.session, student=self.student,
            query='Define a polynomial',
        )

        # Answer still persisted — title stays as the truncated-question default.
        self.assertEqual(self.session.messages.count(), 2)
        self.session.refresh_from_db()
        self.assertEqual(self.session.title, 'Define a polynomial')
        self.assertFalse(result.title_changed)

    @patch('apps.service.services.tutoring.tutor_service.CurriculumRetriever.retrieve')
    @patch('apps.service.services.tutoring.tutor_service.QueryRouter.route')
    def test_chitchat_short_circuits_retrieval(self, mock_route, mock_retrieve):
        mock_route.return_value = Routing(
            subject_ids=[],
            subject_names=[],
            topic_titles=[],
            refined_query='hello',
            intent='chitchat',
            needs_retrieval=False,
            source='llm',
        )

        with patch('clients.llm.LLMService.generate') as mock_generate, \
             patch('clients.llm.LLMService.generate_with_context') as mock_rag:
            mock_generate.return_value = 'Hi! What would you like to learn today?'
            result = TutorService().answer_question(
                session=self.session,
                student=self.student,
                query='hi there',
            )

        mock_retrieve.assert_not_called()
        mock_rag.assert_not_called()
        mock_generate.assert_called_once()
        self.assertEqual(result.assistant_message.retrieved_chunks, [])
        self.assertEqual(result.routing.intent, 'chitchat')


class TutorServiceGuardTests(TestCase):
    """Ownership / tenant guards apply regardless of the LLM key state."""

    @classmethod
    def setUpTestData(cls):
        _bootstrap_roles()

    def setUp(self):
        self.tenant = _create_tenant('springfield')
        self.student = _create_student(self.tenant, 'stu@springfield.test', grade_level=8)
        self.session = TutoringSession.objects.create(tenant=self.tenant, student=self.student)

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
                session=self.session,
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
                session=self.session,
                student=other_student,
                query='Hi',
            )
        mock_retrieve.assert_not_called()


# --------------------------------------------------------------------------- Router unit tests


class QueryRouterTests(TestCase):
    """Exercise the router in isolation (catalog + LLM are fake)."""

    def _catalog(self):
        return [
            SubjectCatalog(
                subject_id=1,
                name='Mathematics',
                code='MATH',
                description='Algebra, geometry, and arithmetic.',
                chapters=[
                    Chapter(node_id='m-ch1', title='Number Systems'),
                    Chapter(node_id='m-ch2', title='Polynomials'),
                    Chapter(node_id='m-ch3', title='Quadratic Equations'),
                ],
            ),
            SubjectCatalog(
                subject_id=2,
                name='Science',
                code='SCI',
                description='Physics, chemistry, and biology.',
                chapters=[
                    Chapter(node_id='s-ch1', title='Motion'),
                    Chapter(node_id='s-ch2', title='Cells'),
                ],
            ),
        ]

    def test_llm_branch_returns_sanitized_routing(self):
        llm = type('DummyLLM', (), {
            'is_configured': True,
            'model': 'gpt-4o-mini',
            'generate_structured': lambda self, **kw: {
                'subject_ids': [1, 99],               # 99 is hallucinated; must be stripped
                'topic_titles': ['Quadratic Equations', 'Not A Chapter'],
                'refined_query': 'Solve x^2 - 3x + 2 = 0',
                'intent': 'problem_solving',
                'needs_retrieval': True,
                'confidence': 0.91,
            },
        })()

        # Deterministic embedding ranking: keep catalog order.
        fake_embed = type('E', (), {
            'embed_text': lambda self, q: [1.0, 0.0, 0.0],
            'embed_batch': lambda self, xs: [[1.0, 0.0, 0.0] for _ in xs],
        })()

        router = QueryRouter(llm_service=llm, embedding_service=fake_embed)
        routing = router.route(
            query='How do I solve this quadratic?',
            catalog=self._catalog(),
            grade_level=8,
        )

        self.assertEqual(routing.source, 'llm')
        self.assertEqual(routing.subject_ids, [1])  # 99 stripped
        self.assertEqual(routing.subject_names, ['Mathematics'])
        self.assertEqual(routing.topic_titles, ['Quadratic Equations'])  # bogus one stripped
        self.assertEqual(routing.intent, 'problem_solving')
        self.assertTrue(routing.needs_retrieval)

    def test_llm_unconfigured_falls_back_to_embedding(self):
        llm = type('DummyLLM', (), {'is_configured': False, 'model': 'x'})()
        fake_embed = type('E', (), {
            'embed_text': lambda self, q: [1.0, 0.0, 0.0],
            'embed_batch': lambda self, xs: [[1.0, 0.0, 0.0] for _ in xs],
        })()

        router = QueryRouter(llm_service=llm, embedding_service=fake_embed)
        routing = router.route(
            query='Explain photosynthesis.',
            catalog=self._catalog(),
            grade_level=8,
        )

        self.assertEqual(routing.source, 'embedding')
        self.assertEqual(len(routing.subject_ids), 1)
        self.assertTrue(routing.needs_retrieval)

    def test_empty_query_returns_no_retrieval(self):
        llm = type('DummyLLM', (), {'is_configured': True, 'model': 'x'})()
        router = QueryRouter(llm_service=llm)
        routing = router.route(query='   ', catalog=self._catalog())
        self.assertFalse(routing.needs_retrieval)
        self.assertEqual(routing.source, 'heuristic')

    def test_empty_catalog_returns_unscoped_retrieval(self):
        llm = type('DummyLLM', (), {'is_configured': True, 'model': 'x'})()
        router = QueryRouter(llm_service=llm)
        routing = router.route(query='tell me about x', catalog=[])
        self.assertTrue(routing.needs_retrieval)
        self.assertEqual(routing.subject_ids, [])
        self.assertEqual(routing.source, 'heuristic')


# --------------------------------------------------------------------------- API


@override_settings(OPENAI_API_KEY='sk-test')
class TutoringAPITests(TestCase):
    """End-to-end checks on the DRF ViewSet, retriever + router + LLM stubbed."""

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

    def test_session_list_orders_latest_activity_first(self):
        """Reproduces the 'latest chat shows at the bottom' bug.

        When sorting purely by `-last_message_at`, an empty new session
        (NULL `last_message_at`) lands above an older session that just
        received a new message, because Postgres DESC puts NULLS FIRST.
        Ordering by COALESCE(last_message_at, created_at) fixes it.
        """
        from datetime import timedelta
        from django.utils import timezone

        now = timezone.now()

        # Oldest session, but just received a fresh message.
        old_active = TutoringSession.objects.create(
            tenant=self.spring, student=self.spring_student, title='old but active',
        )
        TutoringSession.objects.filter(pk=old_active.pk).update(
            created_at=now - timedelta(hours=2),
            last_message_at=now - timedelta(seconds=5),
        )

        # Brand-new empty session (no messages yet -> last_message_at is NULL).
        new_empty = TutoringSession.objects.create(
            tenant=self.spring, student=self.spring_student, title='new empty',
        )
        TutoringSession.objects.filter(pk=new_empty.pk).update(
            created_at=now - timedelta(minutes=1),
        )

        # Truly old session that hasn't been touched.
        really_old = TutoringSession.objects.create(
            tenant=self.spring, student=self.spring_student, title='really old',
        )
        TutoringSession.objects.filter(pk=really_old.pk).update(
            created_at=now - timedelta(days=3),
            last_message_at=now - timedelta(days=1),
        )

        self._login(self.spring_student)
        resp = self.client.get(reverse('service_api:tutoring-session-list'))
        self.assertEqual(resp.status_code, 200)
        titles = [s['title'] for s in resp.json()['data']]

        # Expected: active (5s ago) > new_empty (1 min ago, fallback to created_at)
        # > really_old (1 day ago). The old code would have put 'new empty'
        # first because its last_message_at was NULL.
        self.assertEqual(titles, ['old but active', 'new empty', 'really old'])

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

    def test_create_session_ignores_subject_input(self):
        """Subject selection has been removed from the UX; API ignores it."""
        self._login(self.spring_student)
        url = reverse('service_api:tutoring-session-list')
        resp = self.client.post(
            url,
            data={'subject': self.spring_subject.id, 'title': 'Free exploration'},
            content_type='application/json',
        )

        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertTrue(body['success'])
        # Subject stays None — the router decides per question.
        self.assertIsNone(body['data']['subject'])
        self.assertEqual(body['data']['title'], 'Free exploration')
        self.assertEqual(TutoringSession.objects.filter(student=self.spring_student).count(), 1)

    # -- retrieve / cross-tenant guard ----------------------------------------

    def test_cross_tenant_session_returns_404(self):
        spring_session = TutoringSession.objects.create(
            tenant=self.spring, student=self.spring_student, title='private',
        )
        self._login(self.river_student)
        url = reverse('service_api:tutoring-session-detail', args=[spring_session.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    # -- messages action ----------------------------------------------------

    @patch('clients.llm.LLMService.generate')
    @patch('clients.llm.LLMService.generate_with_context')
    @patch('apps.service.services.tutoring.tutor_service.CurriculumRetriever.retrieve')
    @patch('apps.service.services.tutoring.tutor_service.QueryRouter.route')
    def test_post_message_persists_user_and_assistant(
        self, mock_route, mock_retrieve, mock_llm, mock_generate,
    ):
        mock_route.return_value = _math_routing(self.spring_subject.id)
        mock_retrieve.return_value = _fake_chunks(2)
        mock_llm.return_value = {
            'answer': 'The discriminant is $b^2 - 4ac$ [1].',
            'sources': [],
            'model': 'gpt-4o-mini',
            'timestamp': '2026-04-30T00:00:00Z',
        }
        mock_generate.return_value = 'Quadratic Discriminant'

        session = TutoringSession.objects.create(tenant=self.spring, student=self.spring_student)
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
        self.assertIn('routing', body['data'])
        self.assertEqual(body['data']['routing']['subject_ids'], [self.spring_subject.id])
        self.assertEqual(body['data']['user_message']['role'], 'student')
        self.assertEqual(body['data']['assistant_message']['role'], 'assistant')
        self.assertEqual(body['data']['model'], 'gpt-4o-mini')
        # Real LLM answer — no demo / offline phrasing.
        self.assertIn('discriminant', body['data']['assistant_message']['content'].lower())
        self.assertNotIn('offline mode', body['data']['assistant_message']['content'].lower())

        # Session payload for the sidebar/header title sync.
        self.assertIn('session', body['data'])
        self.assertEqual(body['data']['session']['id'], session.id)
        self.assertEqual(body['data']['session']['title'], 'Quadratic Discriminant')
        self.assertTrue(body['data']['session']['title_changed'])

        self.assertEqual(ChatMessage.objects.filter(session=session).count(), 2)

    @override_settings(OPENAI_API_KEY='')
    def test_post_message_returns_503_when_llm_unconfigured(self):
        """Blocking endpoint must return a clean 503, not an offline stub."""
        session = TutoringSession.objects.create(tenant=self.spring, student=self.spring_student)
        self._login(self.spring_student)
        url = reverse('service_api:tutoring-session-messages', args=[session.id])
        resp = self.client.post(
            url,
            data={'content': "Explain Newton's second law."},
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 503)
        body = resp.json()
        self.assertFalse(body['success'])
        self.assertIn('temporarily unavailable', body['message'].lower())
        # Nothing persisted.
        self.assertEqual(ChatMessage.objects.filter(session=session).count(), 0)

    @patch('apps.service.services.tutoring.tutor_service.CurriculumRetriever.retrieve')
    def test_post_message_validation_error(self, mock_retrieve):
        session = TutoringSession.objects.create(tenant=self.spring, student=self.spring_student)
        self._login(self.spring_student)
        url = reverse('service_api:tutoring-session-messages', args=[session.id])
        resp = self.client.post(url, data={'content': '   '}, content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])
        mock_retrieve.assert_not_called()

    @patch('apps.service.services.tutoring.tutor_service.CurriculumRetriever.retrieve')
    def test_get_messages_returns_history(self, mock_retrieve):
        session = TutoringSession.objects.create(tenant=self.spring, student=self.spring_student)
        ChatMessage.objects.create(session=session, role=ChatMessage.Role.STUDENT, content='hi')
        ChatMessage.objects.create(
            session=session, role=ChatMessage.Role.ASSISTANT,
            content='hello', model='gpt-4o-mini',
        )

        self._login(self.spring_student)
        url = reverse('service_api:tutoring-session-messages', args=[session.id])
        resp = self.client.get(url)

        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body['data']), 2)
        self.assertEqual([m['role'] for m in body['data']], ['student', 'assistant'])
        # Metadata is included now.
        self.assertIn('metadata', body['data'][0])
        mock_retrieve.assert_not_called()

    # -- streaming endpoint -------------------------------------------------

    @staticmethod
    def _fake_llm_stream(chunks):
        """Build a stand-in for `LLMService.generate_with_context(stream=True)`."""
        def _generator(*args, **kwargs):
            for piece in chunks:
                yield piece
        return _generator

    @patch('clients.llm.LLMService.generate_with_context')
    @patch('apps.service.services.tutoring.tutor_service.CurriculumRetriever.retrieve')
    @patch('apps.service.services.tutoring.tutor_service.QueryRouter.route')
    def test_streaming_endpoint_emits_sse_events(self, mock_route, mock_retrieve, mock_llm):
        mock_route.return_value = _math_routing(self.spring_subject.id)
        mock_retrieve.return_value = _fake_chunks(2)
        mock_llm.side_effect = self._fake_llm_stream(['The ', 'discriminant ', 'is $b^2 - 4ac$ [1].'])

        session = TutoringSession.objects.create(tenant=self.spring, student=self.spring_student)
        self._login(self.spring_student)
        url = reverse('service_api:tutoring-session-messages-stream', args=[session.id])

        resp = self.client.post(
            url,
            data={'content': 'What is the discriminant?'},
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/event-stream; charset=utf-8')

        body = b''.join(resp.streaming_content).decode('utf-8')

        # We expect each event type somewhere in the stream.
        for expected in ('event: user_message', 'event: routing', 'event: sources',
                         'event: token', 'event: done', 'event: close'):
            self.assertIn(expected, body, f'missing SSE frame: {expected}')

        # No demo / offline phrasing leaked through.
        self.assertNotIn('offline mode', body.lower())
        self.assertNotIn('no llm configured', body.lower())

        # Both turns should have been persisted once the stream closed.
        self.assertEqual(ChatMessage.objects.filter(session=session).count(), 2)
        last = ChatMessage.objects.filter(
            session=session, role=ChatMessage.Role.ASSISTANT,
        ).first()
        self.assertIsNotNone(last)
        # Full streamed answer was reassembled and persisted.
        self.assertIn('discriminant', last.content.lower())
        # Routing metadata landed on the persisted assistant turn.
        self.assertEqual(last.metadata['routing']['subject_ids'], [self.spring_subject.id])

    @patch('clients.llm.LLMService.generate')
    @patch('clients.llm.LLMService.generate_with_context')
    @patch('apps.service.services.tutoring.tutor_service.CurriculumRetriever.retrieve')
    @patch('apps.service.services.tutoring.tutor_service.QueryRouter.route')
    def test_streaming_endpoint_emits_title_event(
        self, mock_route, mock_retrieve, mock_rag, mock_generate,
    ):
        """First-round SSE streams must emit a `title` event carrying the
        LLM-refined session title + include the session payload in `done`.
        """
        mock_route.return_value = _math_routing(self.spring_subject.id)
        mock_retrieve.return_value = _fake_chunks(2)
        mock_rag.side_effect = self._fake_llm_stream(['The ', 'answer.'])
        mock_generate.return_value = 'Quadratic Formula Explained'

        session = TutoringSession.objects.create(tenant=self.spring, student=self.spring_student)
        self._login(self.spring_student)
        url = reverse('service_api:tutoring-session-messages-stream', args=[session.id])
        resp = self.client.post(
            url,
            data={'content': 'Explain the quadratic formula.'},
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        body = b''.join(resp.streaming_content).decode('utf-8')

        # Dedicated title event + session payload inside `done`.
        self.assertIn('event: title', body)
        self.assertIn('"title": "Quadratic Formula Explained"', body)
        self.assertIn('event: done', body)
        self.assertIn('"session"', body)

        # Title persisted to the row.
        session.refresh_from_db()
        self.assertEqual(session.title, 'Quadratic Formula Explained')

    @patch('clients.llm.LLMService.generate_stream')
    @patch('clients.llm.LLMService.generate_with_context')
    @patch('apps.service.services.tutoring.tutor_service.CurriculumRetriever.retrieve')
    @patch('apps.service.services.tutoring.tutor_service.QueryRouter.route')
    def test_streaming_endpoint_accepts_event_stream_header(
        self, mock_route, mock_retrieve, mock_rag, mock_stream,
    ):
        """Reproduces the browser's `Accept: text/event-stream` request.

        Without the custom `ServerSentEventRenderer` on the @action, DRF's
        content negotiation rejected the header with 406.
        """
        mock_route.return_value = _math_routing(self.spring_subject.id)
        mock_retrieve.return_value = _fake_chunks(1)
        mock_rag.side_effect = self._fake_llm_stream(['hello'])
        mock_stream.side_effect = self._fake_llm_stream(['hello'])

        session = TutoringSession.objects.create(tenant=self.spring, student=self.spring_student)
        self._login(self.spring_student)
        url = reverse('service_api:tutoring-session-messages-stream', args=[session.id])
        resp = self.client.post(
            url,
            data={'content': 'hi'},
            content_type='application/json',
            HTTP_ACCEPT='text/event-stream',
        )
        self.assertEqual(resp.status_code, 200, f'expected 200 with SSE Accept, got {resp.status_code}')
        self.assertTrue(resp['Content-Type'].startswith('text/event-stream'))
        # Drain the stream so the test database commit lands before teardown.
        b''.join(resp.streaming_content)

    @override_settings(OPENAI_API_KEY='')
    def test_streaming_endpoint_emits_error_when_llm_unconfigured(self):
        """Unconfigured LLM → single error frame. No offline / demo text."""
        session = TutoringSession.objects.create(tenant=self.spring, student=self.spring_student)
        self._login(self.spring_student)
        url = reverse('service_api:tutoring-session-messages-stream', args=[session.id])
        resp = self.client.post(
            url,
            data={'content': 'hi'},
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        body = b''.join(resp.streaming_content).decode('utf-8')

        self.assertIn('event: error', body)
        self.assertIn('temporarily unavailable', body.lower())
        self.assertNotIn('offline mode', body.lower())
        self.assertNotIn('no llm configured', body.lower())
        # No messages persisted — the guard runs before the user turn save.
        self.assertEqual(session.messages.count(), 0)

    def test_streaming_endpoint_forbidden_for_non_students(self):
        teacher_role = Role.objects.get(name=Role.TEACHER)
        teacher = User.objects.create_user(
            email='t2@springfield.test', password='Test@1234',
            first_name='T', last_name='Eacher',
            tenant=self.spring, role=teacher_role, is_active=True,
        )
        session = TutoringSession.objects.create(tenant=self.spring, student=self.spring_student)
        self._login(teacher)
        url = reverse('service_api:tutoring-session-messages-stream', args=[session.id])
        resp = self.client.post(url, data={'content': 'hi'}, content_type='application/json')
        # 403 comes from the student-only guard (APIResponse envelope).
        self.assertEqual(resp.status_code, 403)

    # -- destroy ------------------------------------------------------------

    def test_destroy_archives_session(self):
        session = TutoringSession.objects.create(tenant=self.spring, student=self.spring_student)
        self._login(self.spring_student)
        url = reverse('service_api:tutoring-session-detail', args=[session.id])
        resp = self.client.delete(url)
        self.assertEqual(resp.status_code, 200)
        session.refresh_from_db()
        self.assertFalse(session.is_active)


# --------------------------------------------------------------------------- Retriever unit test


class RetrieverFilterTests(TestCase):
    """Confirm the retriever pushes subject filters into the ORM query."""

    @classmethod
    def setUpTestData(cls):
        _bootstrap_roles()

    def setUp(self):
        self.tenant = _create_tenant('springfield')

    @patch.object(CurriculumRetriever, '_pgvector_search')
    def test_subject_ids_forwarded_to_pgvector_search(self, mock_search):
        mock_search.return_value = _fake_chunks(2)

        # Stub the embedder so we never touch the remote service.
        retriever = CurriculumRetriever(embedding_service=type('E', (), {
            'embed_text': lambda self, q: [0.1] * 384,
            'embed_batch': lambda self, xs: [[0.1] * 384 for _ in xs],
        })())

        out = retriever.retrieve(
            tenant=self.tenant,
            query='explain quadratics',
            subject_ids=[7, 9],
            topic_titles=['Polynomials'],
            top_k=4,
        )

        self.assertEqual(len(out), 2)
        kwargs = mock_search.call_args.kwargs
        self.assertEqual(kwargs['subject_ids'], [7, 9])
        self.assertEqual(kwargs['top_k'], 4)
