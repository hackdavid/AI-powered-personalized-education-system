# Project Progress

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
