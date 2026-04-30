# Project Progress

---

## 2026-04-30 (pm): AI Tutor polish — live admin config, clear errors, no demo fallbacks

### What changed

- **Live config reload**: `TutorService._refresh_runtime_config()` re-applies active
  `AppSetting` rows at the top of every tutor request (both blocking and streaming).
  Admins can edit `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL_NAME` in
  `/admin/core/appsetting/` and the tutor picks them up on the next request —
  **no server restart needed**.
- **Whitespace stripping** in `AppSetting.apply_to_settings` + `LLMService.__init__` —
  copy-paste from the admin UI often carries trailing spaces / newlines that
  would silently 401 at LLM time.
- **Differentiated error messages**:
  - `UNAVAILABLE_MESSAGE` → only when `OPENAI_API_KEY` is genuinely empty
    (blocking returns 503, streaming emits a single `error` frame).
  - `build_upstream_error_message(exc)` → includes the concrete exception
    class + truncated message, so students see e.g. "APIStatusError: 404 …"
    and admins can fix the proxy path or model name fast.
- **No more offline/demo content**: `stub_answerer.py` stays deleted. Every
  failure surfaces a real, actionable message.
- **New management command**: `python manage.py check_tutor_config [--test]`
  - Prints the live `AppSetting` rows for tutor keys (even if someone created
    them under the default "other" category instead of `llm`).
  - Shows what `django.conf.settings` actually holds (whitespace-stripped,
    secret values masked).
  - Flags lookalike keys (case typos, stray whitespace).
  - With `--test`, fires a real 1-token LLM call and prints the actual reply
    or exception — the fastest way to tell whether it's a config issue or a
    proxy/network issue.
- **Server log now points to the fix**: when `TutorUnavailable` fires, we log
  the actual state of the `OPENAI_API_KEY` row ("INACTIVE" vs "value=EMPTY"
  vs "No row exists") so the admin can jump straight to the broken field.

### Files

- Modified: `apps/core/models/app_setting.py` (strip whitespace), `apps/service/services/tutoring/{prompts,tutor_service}.py`, `clients/llm/service.py`
- New: `apps/core/management/commands/check_tutor_config.py`

### Test coverage
- 31 / 31 tutor tests pass, including the updated "unavailable" path.

---

## 2026-04-30: AI Tutor — Dynamic Routing, Streaming UX, Markdown+LaTeX Rendering

### What was built

**Backend — two-LLM pipeline with a single model:**
- **LLMService rewrite** (`clients/llm/service.py`): per-call `model` / `temperature` /
  `response_format` overrides; new `generate_stream()` (SSE-ready token iterator),
  `generate_structured()` (JSON mode with regex-extract fallback for endpoints
  that don't honour `response_format`), and `stream=True` on `generate_with_context`.
  Kept `.client`, `._model_name`, `generate()`, `generate_with_context()` surface
  for the ingestion pipeline. Single configurable LLM used across router + answerer.
- **Student catalog** (`apps/service/services/tutoring/catalog.py`): compact
  `[{subject_id, name, chapters: [...]}]` for the student's grade. Uses
  `ClassSubject` ⋈ `ContentNode(node_type='chapter'/'section')` with caps and
  dedup, cached per `(tenant, grade)` in Django cache. Fallback path when
  `ClassSubject` is empty.
- **Query router** (`apps/service/services/tutoring/router.py`): **one LLM call**
  with JSON mode that picks `subject_ids`, `topic_titles`, `refined_query`,
  `intent`, `needs_retrieval`, `confidence`. Pre-filters the catalog to the
  top-N candidate subjects via cosine embedding similarity (no LLM), so the
  classifier prompt stays small. Safe fallbacks (embedding-only routing on LLM
  failure, heuristic routing on empty catalog).
- **Retriever upgrade** (`apps/service/services/tutoring/retriever.py`): now
  talks to `ContentEmbedding` via the ORM directly, pushing the subject filter
  down into the cosine query (no more post-filter in Python). Topic-title
  match boosts score for multi-topic subjects.
- **Prompts** (`apps/service/services/tutoring/prompts.py`): Markdown + KaTeX
  + tables + images + citation rules baked into the answerer system prompt;
  grade / subject / topic / intent-tailored additions; separate small
  chitchat / meta prompts for the short-circuit branch.
- **TutorService refactor** (`tutor_service.py`): `answer_question()` (blocking)
  and `stream_answer()` (SSE event iterator) share one pipeline — catalog →
  router → retriever → answerer. Persists routing metadata on the assistant
  turn via a new `ChatMessage.metadata` JSONField (migration 0005).

**API — SSE streaming:**
- `POST /api/v1/tutoring/sessions/<id>/messages/` still works (blocking, richer
  response includes `routing`).
- **New** `POST /api/v1/tutoring/sessions/<id>/messages/stream/` →
  `text/event-stream`. Event types: `user_message`, `routing`, `sources`,
  `token`, `done`, `error`, `close`.
- **Session creation no longer accepts `subject`** — the router decides per
  question. Old subject param is silently ignored for backward compat.

**Frontend — professional chat UX:**
- **Dropped the subject-picker modal** entirely.
- Added Markdown → DOMPurify → KaTeX → highlight.js → citation rendering
  pipeline (all CDN, no build step): `marked@12`, `DOMPurify@3`, `KaTeX@0.16`
  with `auto-render`, `highlight.js@11` with 8 common languages.
- Full `frontend/static/js/student/chat.js` rewrite: SSE consumer via
  `fetch` + `ReadableStream`, optimistic user bubble, animated "Thinking…"
  indicator until tokens arrive, live re-render of Markdown on each token,
  `[N]` citation chips with hover-tooltip preview + click-to-scroll to the
  matching source row, copy button on assistant turns + on each code block,
  Enter-to-send, Shift+Enter for newline, auto-growing composer.
- Full CSS redesign (`frontend/static/css/student.css`): ChatGPT-style
  layout (student pill right, assistant full-width prose), routing chip,
  sources drawer (collapsible), complete Markdown typography (headings,
  lists, tables, code, blockquotes, images), KaTeX display equations,
  suggestion chips on the empty state.

**Tests:**
- 16 → **24 tests** (all passing). New coverage: router unit tests
  (JSON sanitisation, embedding fallback, empty query / empty catalog),
  SSE endpoint end-to-end, retriever subject-filter forwarding, chitchat
  short-circuit, routing metadata persistence on both stub and LLM branches.

### Files

- New: `apps/service/services/tutoring/catalog.py`
- New: `apps/service/services/tutoring/router.py`
- New migration: `apps/service/migrations/0005_chatmessage_metadata.py`
- Rewritten: `clients/llm/service.py`, `apps/service/services/tutoring/{tutor_service,retriever,prompts,__init__}.py`, `apps/service/api/tutoring.py`, `apps/service/api/serializers.py`, `frontend/templates/student/chat.html`, `frontend/static/js/student/chat.js`, `frontend/static/css/student.css`, `apps/web/views/student/chat.py`, `apps/service/tests/test_tutoring.py`
- Modified: `apps/service/models/tutoring.py` (added `ChatMessage.metadata`)

---

## 2026-04-20: School Admin Portal COMPLETE

### What was built
- **Classes management**: CRUD for classes with grade/section/year/teacher, slide-in panel for add/edit
- **Subjects management**: CRUD for subjects with color codes, slide-in panel
- **Class-Subject assignment**: Assign subjects + teachers to classes from class detail page
- **Teacher management**: Invite teachers with auto-generated credentials shown on screen, edit, activate/deactivate
- **Student management**: Invite students with auto-generated credentials shown on screen, edit, activate/deactivate
- **Books/Documents**: Upload PDF/DOCX files with subject/class metadata, list, delete
- **Dashboard**: Updated with real stats (users/students/teachers/classes counts), working sidebar links

### New App: `apps/school_admin/`
- `apps.py`, `__init__.py`
- `forms.py` — ClassForm, SubjectForm, ClassSubjectForm, TeacherInviteForm, StudentInviteForm, DocumentUploadForm
- `urls.py` — All CRUD routes under `/school-admin/`
- `views/class_views.py` — Class CRUD + subject assignment
- `views/subject_views.py` — Subject CRUD
- `views/teacher_views.py` — Teacher invite/list/edit/toggle
- `views/student_views.py` — Student invite/list/edit/toggle
- `views/document_views.py` — Document upload/list/delete

### New Model: `apps/common/models/document.py`
- `Document` model (TenantAwareModel + AuditModel) for book uploads with file, status, subject/class FKs

### Templates (6 pages)
- `school_admin/classes/list.html` — Class table + add/edit slide-in panels
- `school_admin/classes/detail.html` — Class detail + subject assignments
- `school_admin/subjects/list.html` — Subject table + add/edit slide-in panels
- `school_admin/teachers/list.html` — Teacher table + invite/edit panels + credential card
- `school_admin/students/list.html` — Student table + invite/edit panels + credential card
- `school_admin/documents/list.html` — Document table + upload panel

### CSS
- `frontend/static/css/school_admin.css` — Slide-in panels, data tables, badges, credential card, form inputs, empty states

### Files Modified
- `config/settings/base.py` — Added `apps.school_admin` to INSTALLED_APPS
- `config/urls.py` — Added school_admin URL patterns
- `apps/common/models/__init__.py` — Added Document export
- `apps/core/views.py` — Dashboard router now passes real stats to school_admin dashboard
- `frontend/templates/dashboards/school_admin_dashboard.html` — Working sidebar links + real stats

### Migration
- `apps/common/migrations/0002_document.py` — Creates Document table

---

## 2026-04-20: Phase 2 - AI Services Layer COMPLETE

### Files Created
- `services/__init__.py` - Package init
- `services/apps.py` - AppConfig that pre-loads embedding model on server startup
- `services/ai/__init__.py` - Package init
- `services/ai/llm_service.py` - OpenAI-compatible LLM with configurable base_url, model_name, api_key
- `services/ai/embedding_service.py` - Free sentence-transformers embedding (all-MiniLM-L6-v2, 384-dim)
- `services/ai/question_generator.py` - AI question generation (MCQ, true/false, short answer, essay)
- `services/vector_store/__init__.py` - Package init
- `services/vector_store/client.py` - Local ChromaDB with PersistentClient, auto-embedding search

### Files Modified
- `config/settings/base.py` - Added OPENAI_BASE_URL, OPENAI_MODEL_NAME, EMBEDDING_MODEL_NAME, CHROMADB_PERSIST_DIR; added 'services' to INSTALLED_APPS
- `.env.example` - Added OPENAI_BASE_URL, OPENAI_MODEL_NAME, EMBEDDING_MODEL_NAME, CHROMADB_PERSIST_DIR
- `requirements/base.txt` - Uncommented sentence-transformers

### Testing
- Embedding: `from services.ai.embedding_service import get_embedding_service; s = get_embedding_service(); print(s.embed_text("hello"))`
- LLM: `from services.ai.llm_service import LLMService; llm = LLMService(); print(llm.generate("Say hi"))`
- Vector Store: `from services.vector_store.client import VectorStoreClient; c = VectorStoreClient(); print(c.list_collections())`
- Questions: `from services.ai.question_generator import QuestionGenerator; qg = QuestionGenerator(); print(qg.generate_questions("Python", "easy", 2, "mcq"))`

---
## 2026-04-20: Project Analysis & CLAUDE.md Setup

- Analyzed full eduai_platform codebase structure
- Created CLAUDE.md in `code_base/eduai_platform/` with project overview, conventions, and rules
- Created this progress.md file for tracking work
- Updated memory.md with project state

### Current Project Status

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | Core infrastructure, auth, RBAC, multi-tenancy, frontend utils, dashboards | COMPLETE |
| Phase 2 | AI services (LLM, embeddings, vector store, ChromaDB) | COMPLETE |
| Phase 3 | Feature apps (ingestion, tutoring, assessments, analytics, goals) | NOT STARTED |
| Phase 4 | Production readiness (Celery, Redis, S3, comprehensive testing) | NOT STARTED |

---
