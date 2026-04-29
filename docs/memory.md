# EduAI Platform — Memory

Abstract durable knowledge. The stuff future-me (or any LLM picking up this
repo) needs to know without having to read every file. Read this once, then
write features.

## 1. Project shape

```
eduai_platform/
├── manage.py
├── requirements.txt         # SINGLE requirements file, all environments
├── .env.example             # copy → .env, fill in secrets
├── .env.local.example       # 3-line minimal version for new contributors
├── Dockerfile               # production runtime image (Render)
├── .dockerignore
├── render.yaml              # Render service blueprint
├── config/
│   ├── settings.py          # SINGLE settings file; DEBUG flag toggles env
│   ├── urls.py              # top-level URL patterns
│   ├── wsgi.py, asgi.py
├── apps/
│   ├── core/                # Infrastructure: base models, middleware,
│   │                        # decorators, APIResponse, health check,
│   │                        # AppSetting (runtime-overridable settings).
│   ├── accounts/            # Identity: User, Role, Permission, Tenant,
│   │                        # AuthService, RBACService.
│   ├── service/             # Domain: models + business services + REST APIs.
│   │                        # Where ingestion / tutoring / assessments /
│   │                        # analytics / goals all live as service modules.
│   └── web/                 # Presentation: HTML views, forms, dashboards,
│                            # auth pages. Owns no models.
├── clients/                 # External adapters (NOT a Django app):
│                            #   llm/, embeddings/, vector_store/, storage/.
├── frontend/
│   ├── static/              # css/, js/core/, vendor/
│   └── templates/           # base/, components/, dashboards/, auth/, school_admin/, student/
├── fixtures/                # synthetic book YAMLs
├── logs/                    # app.log
└── docs/                    # project_aim.md, memory.md, progress.md, todo.md
```

Rule of thumb: **plumbing → core, who → accounts, what → service, screens → web,
external → clients/**.

## 2. Tech stack

| Layer | Choice |
|---|---|
| Framework | Django 4.2, Python 3.9+ |
| DB (dev) | SQLite |
| DB (prod) | PostgreSQL |
| Cache (prod) | Redis |
| LLM | OpenAI-compatible API (works for OpenAI, Azure OpenAI, Ollama) |
| Embeddings (default) | Remote: `eduai-embedder` HuggingFace Space (FastAPI + sentence-transformers, 384-dim). Repo lives outside `eduai_platform/`. |
| Embeddings (fallback) | Local: sentence-transformers `all-MiniLM-L6-v2` (`pip install -r requirements/embeddings-local.txt`) |
| Vector store | pgvector on Supabase Postgres (HNSW cosine, 384-dim); legacy ChromaDB code path removed in Phase 3C |
| Async (planned) | Celery + Redis |
| Static (prod) | WhiteNoise + CompressedManifestStaticFilesStorage |
| Error tracking | Sentry (prod only, opt-in via `SENTRY_DSN`) |
| Deploy target | Render (Docker runtime, autoDeploy from `main`); see `docs/deployment.md` |
| Frontend | Vanilla ES6, no React/Vue, no jQuery |

## 3. Roles & access

Four roles, defined as DB rows, codified in `accounts.Role`:

| Role | Code | Hierarchy level | Sees |
|---|---|---|---|
| Student | `student` | 1 | own data only |
| Teacher | `teacher` | 2 | own classes / assigned students |
| School Admin | `school_admin` | 3 | own tenant only |
| System Admin | `system_admin` | 4 | all tenants |

Two **separate** admin concepts:
- **Django superuser** (`is_superuser=True`) — technical admin. Can hit
  `/admin/`. Created via `python manage.py createsuperuser`. Treated as
  super-system-admin in the dashboard router.
- **System Admin** — business admin role. Cannot access `/admin/`. Created
  via `python manage.py create_system_admin`.

`User` properties already exposed for templates:
`user.is_student`, `user.is_teacher`, `user.is_school_admin`,
`user.is_system_admin`, `user.is_django_superuser`, `user.role_name`.

## 4. Core contracts (memorize these)

### `APIResponse` — the JSON envelope for every API endpoint

`from apps.core.utils.response import APIResponse`

Every JSON response in the system has this shape:

```json
{
  "success": true,
  "message": "...",
  "data": {...} | null,
  "errors": {...} | null,
  "timestamp": "ISO-8601"
}
```

API:
- `APIResponse.success(data=None, message="", status=200, **kwargs)`
- `APIResponse.error(message, errors=None, status=400, **kwargs)`
- Convenience: `not_found()`, `forbidden()`, `unauthorized()`,
  `validation_error(errors, message)`, `server_error()`.

### Base models — every model inherits from one or more of these

`from apps.core.models.base import (TimestampedModel, TenantAwareModel, AuditModel, SoftDeleteModel)`

- `TimestampedModel` → `created_at`, `updated_at`.
- `TenantAwareModel` → adds `tenant` FK, validates tenant on save.
- `AuditModel(TimestampedModel)` → adds `created_by`, `updated_by`.
- `SoftDeleteModel` → adds `is_deleted`, `deleted_at`, `deleted_by`,
  `soft_delete()`, `restore()`.

**Rule:** any data row that belongs to a school must extend `TenantAwareModel`.
Anything user-edited where attribution matters extends `AuditModel`.

### Decorators — view protection

`from apps.core.decorators import role_required, tenant_required, log_action, ajax_required`

- `@role_required(['teacher', 'school_admin'])` — restricts by role name.
- `@tenant_required` — fails if `request.tenant` is unset.
- `@log_action('create_assignment')` — structured-log the action.
- `@ajax_required` — fails non-AJAX requests with 400.

### Auth & RBAC services

`from apps.accounts.services.auth_service import AuthService`
`from apps.accounts.services.rbac_service import RBACService`

`AuthService` handles login/logout/password lifecycle. `RBACService` handles
permission checks, tenant gating, and queryset filtering by role.

### TutorService — RAG entry point (Phase 2)

`from apps.service.services.tutoring import TutorService`

Single canonical entry point for the AI tutor. `answer_question(session,
student, query, top_k=5)` runs one full Q&A round in a transaction:
persists the student turn, retrieves grounded chunks from the tenant's
`<tenant_id>_curriculum` ChromaDB collection, calls
`clients.llm.LLMService.generate_with_context` when `OPENAI_API_KEY` is
set (stub answerer otherwise), persists the assistant turn with the
retrieved chunks, refreshes `session.last_message_at`, and auto-titles
the session from the first question. Empty queries raise `ValueError`;
cross-student / cross-tenant sessions raise `PermissionError`. The DRF
`TutoringSessionViewSet` is its only caller in production code.

## 5. Frontend contracts

All four utilities live under `frontend/static/js/core/` and are loaded by
`base.html`. No npm, no bundler.

| Utility | Class | What it does |
|---|---|---|
| `api-client.js` | `APIClient` | `get/post/put/delete`. Auto CSRF. Auto Toast on error. Returns `{success, data, message, errors}`. |
| `toast.js` | `Toast` | `success/error/info/loading/show`. Mounts to `#toast-container`. |
| `forms.js` | `FormHandler` | `FormHandler.initialize(formEl, {onSuccess, onError, url, method})`. Loading state + AJAX submit. |
| `modal.js` | `Modal` | `Modal.confirm({title, message})` returns a Promise<bool>. |

**Rule:** never write raw `fetch` or `XMLHttpRequest`. Use `APIClient`.
Never write your own toast popups.

## 6. Multi-tenancy — how it works

- `apps.core.middleware.tenant_middleware.TenantMiddleware` runs on every
  request and sets `request.tenant`. Resolution order:
  1. From subdomain (e.g. `springfield.platform.com` → tenant slug
     `springfield`).
  2. From `request.user.tenant` if authenticated and no subdomain match.
- `TenantAwareModel.save()` refuses to save without a tenant.
- ChromaDB collections are namespaced as `<tenant_id>_<collection_name>` — so
  even at the vector layer schools are isolated.
- `RBACService.filter_by_role_access(qs, user)` is the canonical helper for
  auto-filtering a queryset to what the user is allowed to see.

## 7. Naming conventions

- Python: PEP 8, type hints on public functions, `black` formatter.
- Django: one model per file under `models/` folder, with `models/__init__.py`
  re-exporting the symbols.
- Apps stay singular and noun-shaped: `core`, `accounts`, `service`, `web`.
- Services live in `apps/<app>/services/<feature>/<service_name>.py`.
- View modules under `apps/web/views/<role>/<resource>.py`.
- URL namespaces match app names: `core:`, `auth:`, `web:`, `service_api:` (when
  added).
- JS: ES6+, classes `PascalCase`, vars `camelCase`, files `kebab-case.js`.
- No docstrings on obvious code; comment only the non-obvious WHY.

## 8. Config & environment variables

Single `config/settings.py`. `DJANGO_DEBUG` switches between dev and prod
behaviour (SQLite fallback, console email, dummy cache, relaxed security)
and specific overrides happen only when `DJANGO_DEBUG=False`. All vars
loaded by `python-decouple` from `.env` (see `.env.example`).

| Key | Default | Notes |
|---|---|---|
| `DJANGO_SECRET_KEY` | insecure placeholder | **required in prod** |
| `DJANGO_DEBUG` | `False` | `True` in dev |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | comma-separated |
| `DATABASE_URL` | _(empty)_ | Postgres URL (Supabase **transaction pooler**, port `6543`). Empty → SQLite in dev; **required in prod**. See note below. |
| `OPENAI_API_KEY` | _(none)_ | required for grounded tutor answers (else stub mode) |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | swap for Azure/Ollama/etc. |
| `OPENAI_MODEL_NAME` | `gpt-4` | LLM to use |
| `ANTHROPIC_API_KEY` | _(none)_ | Optional fallback |
| `LLM_PROVIDER` | `openai` | switch provider |
| `EMBEDDING_PROVIDER` | `remote` | `remote` (HF Space) or `local` (sentence-transformers) |
| `EMBEDDER_API_URL` | _(none)_ | required when provider=remote |
| `EMBEDDER_API_KEY` | _(none)_ | shared secret matching the Space's `EMBEDDER_API_KEY` |
| `EMBEDDING_MODEL_NAME` | `all-MiniLM-L6-v2` | sentence-transformers (local provider only) |
| `EMBEDDING_MODEL_PRELOAD` | `False` | preload at app start (local provider only) |
| `VECTOR_STORE_TYPE` | `pgvector` | only backend supported today |
| `REDIS_URL` | _(none)_ | prod only; Redis cache enabled when set |
| `SENTRY_DSN` | _(none)_ | prod only; opt-in error tracking |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | _(none)_ | prod only; dev uses console backend |
| `LOG_FILE` | `BASE_DIR/logs/app.log` | JSON-lines output |
| `SEED_DEFAULT_PASSWORD` | `Test@1234` | synthetic user password |

**Runtime overrides**: most AI-service keys (the LLM / embedder block)
are overridden from the DB via `AppSetting` at server startup. See §14
for the resolution order. `.env` acts as the fallback for any key
without an active `AppSetting` row.

### Supabase connection mode (important)

Use the **session-mode pooler URL (port `5432`)** for migrations only,
and the **transaction-mode pooler URL (port `6543`)** for everything
else. Free tier session mode caps at **15 concurrent connections**;
transaction mode supports ~200.

Settings already do the right thing:
- `conn_max_age=0` — Django closes the socket after each request
- `disable_server_side_cursors=True` — cursors don't survive transaction-pool boundaries

Day-to-day URL in `.env`:

```
DATABASE_URL=postgresql://postgres.<ref>:<pwd>@aws-0-<region>.pooler.supabase.com:6543/postgres
```

When you run `python manage.py migrate`, temporarily flip the port to
`5432` (session mode), apply, then flip back to `6543`. Most migrations
work on either, but session mode is the safer default for schema
changes.

## 9. Key URLs (top-level routing)

```
/                                                      → web.public.home
/dashboard/                                            → web.dashboards.dashboard_router (role-aware)
/auth/login/                                           → web.auth.login_view
/auth/logout/                                          → web.auth.logout_view
/auth/password-change/                                 → web.auth.password_change_view
/auth/password-reset/                                  → web.auth.password_reset_request_view
/school-admin/...                                      → web.school_admin.* (CRUD UIs)
/student/chat/                                         → web.student.chat.chat_view
/student/chat/<session_id>/                            → web.student.chat.chat_view (active session)
/health/                                               → core.health_check (JSON)
/admin/                                                → Django admin (superuser only)
/api/v1/tutoring/sessions/                             → service_api:tutoring-session-list (POST | GET)
/api/v1/tutoring/sessions/<id>/                        → service_api:tutoring-session-detail (GET | DELETE)
/api/v1/tutoring/sessions/<id>/messages/               → service_api:tutoring-session-messages (GET | POST)
```

## 10. Ingestion pipeline (already built, lives under `apps/service/services/ingestion/`)

5-stage hybrid pipeline (text + vision):

| Stage | Class | Purpose |
|---|---|---|
| 0 | `PDFRenderer` | extract text per page, render page images, extract image assets |
| 1 | `TOCDiscovery` + `PageCalibrator` | LLM-extract TOC, calibrate printed→PDF page indices |
| 2 | `ChapterOutliner` + `ContentStructurer` | LLM-outline sections; vision LLM extracts content nodes (chapter/section/topic/definition/formula/example/exercise/summary/key_point) |
| 3 | `ImageLinker` | attach image assets to relevant content nodes |
| 4 | `ContentStorage` | persist nodes + assets, generate embeddings via the HF Space, upsert `ContentEmbedding` rows into Supabase pgvector |
| 5 | `CrossRefBuilder` | build prerequisite/related/extends/applies links between nodes |

Orchestrator: `IngestionPipeline(skip_vision, max_pages).run(document_id) -> stats dict`.

Math content is enforced as LaTeX. Embeddings dim = 384, L2-normalized
(cosine = dot product). Every `ContentEmbedding` row is scoped by `tenant`;
the legacy `<tenant_id>_curriculum` collection naming lingers only in the
seeding command's log output.

CLI (today): `python manage.py ingest_document <document_id> [--skip-vision] [--max-pages N] [--list] [--force]`.

REST endpoint: not yet exposed (see todo.md Phase 1).

## 11. Standard run commands

```bash
# Setup
python -m venv venv
venv\Scripts\activate                       # Windows
# source venv/bin/activate                  # macOS/Linux
pip install -r requirements.txt             # SINGLE requirements file
copy .env.example .env                      # Windows
# cp .env.example .env                      # macOS/Linux

# DB + seed
python manage.py migrate
python manage.py create_roles
python manage.py createsuperuser            # Django superuser (technical)
python manage.py create_system_admin        # System admin (business)
python manage.py bootstrap_app_settings --include-secrets   # populate AppSetting from .env
python manage.py seed_synthetic_data --reset               # 2 demo tenants + users + classes + books
# Required for the AI tutor: also embed every ContentNode into the vector
# store so RAG retrieval has anything to find.
# python manage.py seed_synthetic_data --reset --with-embeddings

# Run
python manage.py runserver                  # http://127.0.0.1:8000/
python manage.py test apps                  # run all app tests (46 passing)
python manage.py ingest_document <id>       # ingest one real PDF (Phase 6)
```

Default password for synthetic users is `Test@1234` (override with
`SEED_DEFAULT_PASSWORD` env var). Demo school admins:
`admin@springfield.test`, `admin@riverside.test`.

Windows shortcuts: `setup.bat` (one-shot install) and `run.bat` (start
server) at project root.

## 12. Things NOT to do

- Don't put business logic in views. Views call services.
- Don't put templates / forms / dashboards in `apps/service/`. Those go in
  `apps/web/`.
- Don't import from `apps.web.*` inside `apps/service/*` or `apps/accounts/*`.
  Dependency direction is `web → service → accounts → core` and
  `web/service → clients/`.
- Don't talk to `openai`, `pgvector`, `requests`, or `sentence_transformers`
  directly from domain code. Always go through `clients/`.
- Don't build a model that owns school-scoped data without extending
  `TenantAwareModel`.
- Don't write raw `fetch` / `JSON.stringify` in JS. Use `APIClient`.
- Don't add new top-level MD files. Append to `docs/progress.md` and update
  `docs/memory.md` instead.

## 13. Useful pointers

- Login redirects to `/dashboard/` which dispatches by role.
- Health endpoint at `/health/` checks DB connectivity (extend it when adding
  new external dependencies). Render uses it as the readiness probe.
- All migrations were regenerated as part of the Phase 0 refactor (see
  progress.md). If `db.sqlite3` looks broken, delete it + re-run migrate.
- Logs go to `logs/app.log` as JSON lines.
- Deploy: connect the GitHub repo to Render → it picks up `render.yaml`
  → set `DATABASE_URL` and `EMBEDDER_API_KEY` as Render secrets → autoDeploy
  on every push to `main`. Full walkthrough in `docs/deployment.md`.

## 14. Runtime settings via `AppSetting` (admin-editable config)

A subset of `django.conf.settings` attributes can be overridden from the
DB via the `AppSetting` model in `apps.core`. Lets one admin manage API
keys / external URLs through Django admin without sharing the secret
values with every team-mate's `.env`.

### How resolution works

1. `config/settings/base.py` reads `.env` (via python-decouple) at import
   time — same as before.
2. `apps.core.apps.CoreConfig.ready()` runs once at server startup, reads
   every `AppSetting` row where `is_active=True`, and overwrites the
   matching `settings.<key>` attribute via `setattr`.
3. Existing code that does `from django.conf import settings;
   settings.OPENAI_API_KEY` transparently sees the DB value.

**Order of precedence**: active DB row > `.env` > default in `base.py`.

**To change a value**: edit it in `/admin/core/appsetting/`, then restart
the server. No code change, no `.env` edit required.

### What's overridable

The single source of truth is `REGISTRY` in
`apps/core/management/commands/bootstrap_app_settings.py`. As of now:
`OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL_NAME`,
`ANTHROPIC_API_KEY`, `LLM_PROVIDER`, `EMBEDDING_PROVIDER`,
`EMBEDDER_API_URL`, `EMBEDDER_API_KEY`, `EMBEDDING_MODEL_NAME`,
`VECTOR_STORE_TYPE`. All string-valued; **never put bool / int settings
here** (the override is `setattr(settings, key, db_value)` and `db_value`
is always a string).

### Bootstrap

Run once after migrations land on a fresh checkout:

```bash
python manage.py bootstrap_app_settings              # public values only
python manage.py bootstrap_app_settings --include-secrets   # also copy keys from your .env
```

Idempotent. Re-running adds new keys (when REGISTRY grows) without
touching values you've already curated in admin.

### What stays in `.env` forever

`DJANGO_SECRET_KEY`, `DATABASE_URL`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`,
`SEED_DEFAULT_PASSWORD`. These are read before the DB is reachable, or
need to be cast to non-string types (bool, int) at import time, so they
can't be DB-managed without breaking startup.
