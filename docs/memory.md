# EduAI Platform — Memory

Abstract durable knowledge. The stuff future-me (or any LLM picking up this
repo) needs to know without having to read every file. Read this once, then
write features.

## 1. Project shape

```
eduai_platform/
├── manage.py
├── config/                  # Django project (settings, urls, wsgi, asgi)
├── apps/
│   ├── core/                # Infrastructure: base models, middleware,
│   │                        # decorators, APIResponse, health check.
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
│   └── templates/           # base/, components/, dashboards/, auth/, school_admin/
├── requirements/            # base.txt, development.txt, production.txt
├── tests/                   # unit/, integration/, e2e/
├── fixtures/                # JSON fixtures
├── logs/                    # app.log
├── docs/                    # project_aim.md, memory.md, progress.md, todo.md
└── chroma_data/             # ChromaDB persistent dir (gitignored)
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
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` (free, local, 384-dim) |
| Vector store | ChromaDB PersistentClient (local, no server needed) |
| Async (planned) | Celery + Redis |
| Static (prod) | WhiteNoise + CompressedManifestStaticFilesStorage |
| Error tracking | Sentry (prod only) |
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

Loaded by `python-decouple` from `.env`. Required keys:

| Key | Default | Notes |
|---|---|---|
| `DJANGO_SECRET_KEY` | _(none)_ | Required |
| `DJANGO_DEBUG` | `False` | `True` in dev |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | comma-separated |
| `DATABASE_URL` | sqlite | Required in prod |
| `OPENAI_API_KEY` | _(none)_ | Required for tutoring |
| `OPENAI_BASE_URL` | OpenAI default | Set for Azure/Ollama |
| `OPENAI_MODEL_NAME` | `gpt-4` | LLM to use |
| `ANTHROPIC_API_KEY` | _(none)_ | Optional fallback |
| `LLM_PROVIDER` | `openai` | switch provider |
| `EMBEDDING_MODEL_NAME` | `all-MiniLM-L6-v2` | sentence-transformers |
| `EMBEDDING_MODEL_PRELOAD` | `False` | preload at app start |
| `VECTOR_STORE_TYPE` | `chromadb` | only chromadb today |
| `CHROMADB_PERSIST_DIR` | `BASE_DIR/chroma_data` | gitignored |
| `REDIS_URL` | _(none)_ | prod only |
| `SENTRY_DSN` | _(none)_ | prod only |

## 9. Key URLs (top-level routing)

```
/                         → web.public.home
/dashboard/               → web.dashboards.dashboard_router (role-aware)
/auth/login/              → web.auth.login_view
/auth/logout/             → web.auth.logout_view
/auth/password-change/    → web.auth.password_change_view
/auth/password-reset/     → web.auth.password_reset_request_view
/school-admin/...         → web.school_admin.* (CRUD UIs)
/health/                  → core.health_check (JSON)
/admin/                   → Django admin (superuser only)
/api/v1/...               → service.api.* (when REST layer lands)
```

## 10. Ingestion pipeline (already built, lives under `apps/service/services/ingestion/`)

5-stage hybrid pipeline (text + vision):

| Stage | Class | Purpose |
|---|---|---|
| 0 | `PDFRenderer` | extract text per page, render page images, extract image assets |
| 1 | `TOCDiscovery` + `PageCalibrator` | LLM-extract TOC, calibrate printed→PDF page indices |
| 2 | `ChapterOutliner` + `ContentStructurer` | LLM-outline sections; vision LLM extracts content nodes (chapter/section/topic/definition/formula/example/exercise/summary/key_point) |
| 3 | `ImageLinker` | attach image assets to relevant content nodes |
| 4 | `ContentStorage` | persist nodes + assets, generate embeddings, upsert to ChromaDB |
| 5 | `CrossRefBuilder` | build prerequisite/related/extends/applies links between nodes |

Orchestrator: `IngestionPipeline(skip_vision, max_pages).run(document_id) -> stats dict`.

Math content is enforced as LaTeX. Embeddings dim = 384. Collection name =
`<tenant_id>_curriculum`.

CLI (today): `python manage.py ingest_document <document_id> [--skip-vision] [--max-pages N] [--list] [--force]`.

REST endpoint: not yet exposed (see todo.md Phase 1).

## 11. Standard run commands

```bash
# Setup
python -m venv venv
venv\Scripts\activate                       # Windows
# source venv/bin/activate                  # macOS/Linux
pip install -r requirements/development.txt
copy .env.example .env                      # Windows
# cp .env.example .env                      # macOS/Linux

# DB + seed
python manage.py migrate
python manage.py create_roles
python manage.py createsuperuser            # Django superuser (technical)
python manage.py create_system_admin        # System admin (business)
python manage.py seed_synthetic_data --reset        # 2 demo tenants + users + classes + books
# python manage.py seed_synthetic_data --reset --with-embeddings  # also embed into ChromaDB

# Run
python manage.py runserver                  # http://127.0.0.1:8000/
python manage.py test apps.service          # run service-app tests (incl. seeding tests)
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
- Don't talk to `openai`, `chromadb`, or `sentence_transformers` directly from
  domain code. Always go through `clients/`.
- Don't build a model that owns school-scoped data without extending
  `TenantAwareModel`.
- Don't write raw `fetch` / `JSON.stringify` in JS. Use `APIClient`.
- Don't add new top-level MD files. Append to `docs/progress.md` and update
  `docs/memory.md` instead.

## 13. Useful pointers

- Login redirects to `/dashboard/` which dispatches by role.
- Health endpoint at `/health/` checks DB connectivity (extend it when adding
  new external dependencies).
- All migrations were regenerated as part of the Phase 0 refactor (see
  progress.md). If `db.sqlite3` looks broken, delete it + re-run migrate.
- Logs go to `logs/app.log` as JSON lines.
