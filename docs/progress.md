# EduAI Platform — Progress

Append-only ledger of shipped work. Newest entries at the top. Each entry:
**date** • **scope** • **what** • **where**.

---

## Phase 1 — Synthetic data + schema hardening _(complete)_

- **2026-04-27 • schema** • Two-field tweak on `service.Document` so
  synthetic books can stand alone:
  - `Document.file` is now `blank=True, null=True`.
  - New `Document.source_type` (`'pdf' | 'synthetic'`, default `'pdf'`,
    indexed on `(tenant, source_type)`).
  - New `Document.SourceType` `TextChoices` enum.
  - `apps/service/admin.py::DocumentAdmin` exposes `source_type` in both
    `list_display` and `list_filter`.
  - Migration: `service.0002_document_source_type_alter_document_file_and_more`.
  - No other model changes; the existing `Document → ContentNode →
    Asset / ContentCrossRef` shape was already correct for synthetic
    content.
- **2026-04-27 • deps** • Added `PyYAML` to `requirements/base.txt`.
  `faker` was already in `requirements/development.txt` (used at seed
  time only).
- **2026-04-27 • content** • Six starter book YAMLs at
  `fixtures/synthetic_books/`:
  - `math-grade-8.yaml`, `math-grade-9.yaml`
  - `science-grade-8.yaml`, `science-grade-9.yaml`
  - `english-grade-8.yaml`, `english-grade-9.yaml`
  Each book: 2 chapters × 2 sections × 1–2 topics × 2–4 leaves, with at
  least one markdown table per book and 2 cross-references.
- **2026-04-27 • services** • New seeding package
  `apps/service/services/seeding/`:
  - `tenants.py` — `seed_tenants(slugs)` (default `springfield`,
    `riverside`); `reset_tenant_synthetic_data(tenant)` deletes only
    `source_type='synthetic'` documents.
  - `users.py` — `seed_users(tenant)` builds 1 school_admin + 10 teachers
    + 80 students with `faker` (deterministic via `Faker.seed`),
    idempotent on email (`first.last@<slug>.test`). Default password
    from `SEED_DEFAULT_PASSWORD` env, fallback `Test@1234`.
  - `classes.py` — `seed_subjects` (5 default subjects: MATH, SCI, ENG,
    HIST, GEO), `seed_classes` (grades 8 & 9, sections A & B,
    auto-derived academic year), `seed_class_subjects`.
  - `books.py` — discovers `.yaml` files, builds `Document` rows
    (`source_type='synthetic'`, `status='completed'`, `file=None`),
    recursively builds the `ContentNode` tree with `parent` links and
    structured `node_id` paths (`ch1.s2.t1.l3`), then resolves
    `cross_refs` into `ContentCrossRef`. Wipes + rebuilds the tree per
    book on every run so the YAML is the source of truth.
  - `submissions.py` — Phase 4 stub.
- **2026-04-27 • cli** • New management command
  `python manage.py seed_synthetic_data` with flags `--tenant` (repeatable),
  `--reset`, `--books-only`, `--users-only`, `--with-embeddings`,
  `--seed`. Pre-flights that the four roles exist (`create_roles` must
  have run first). The `--with-embeddings` flag wires
  `clients.embeddings` + `clients.vector_store` to populate the tenant's
  `<tenant_id>_curriculum` ChromaDB collection (free local
  sentence-transformers, off by default).
- **2026-04-27 • verification** • Full seed produces:
  `tenants=2  users=+182  (1 SA + 10 T + 80 S per tenant)
  subjects=10  classes=8  class_subjects=40  books=12  chapters=24
  sections=38  topics=40  leaves=108  cross_refs=24`. Tenant isolation
  verified by cross-querysets returning 0 rows.
- **2026-04-27 • tests** • New integration tests at
  `apps/service/tests/test_seeding.py`. Five tests, all passing on
  Django's built-in test runner (`python manage.py test apps.service`):
  full-seed-counts, idempotency, tenant isolation, book discovery,
  content-tree node types.

### Tally update

- **Models in DB**: unchanged at 11 (Document gained one field +
  one index, but no new models).
- **Lines of Python**: +~700 (seeding services + management command +
  tests).
- **Synthetic content**: 6 YAML books, 12 chapters, 38 sections, 40
  topics, 108 leaves of structured curriculum content, 24 cross-refs
  per full seed (across both tenants).
- **Management commands**: now `create_roles`, `create_system_admin`,
  `ingest_document`, **`seed_synthetic_data`**.

---

## Phase 0 — Refactor & cleanup _(complete)_

- **2026-04-27 • docs** • Consolidated 13 scattered root-level MD files (CLAUDE,
  README, QUICKSTART, QUICK_REFERENCE, START_HERE, SETUP_AND_TEST, FIXED_SETUP,
  PHASE1_COMPLETE, LANDING_PAGE_COMPLETE, ADMIN_SEPARATION_COMPLETE,
  SUPERUSER_VS_SYSTEMADMIN, SHARING_DATA, PROJECT_STRUCTURE.txt) plus parent
  `IMPLEMENTATION_PLAN.md` and `overview.txt` into 4 living docs:
  `docs/project_aim.md`, `docs/memory.md`, `docs/progress.md`, `docs/todo.md`.
  Root `README.md` shrunk to a thin pointer.
- **2026-04-27 • structure** • Collapsed the 10-app sprawl into a clean 4-app
  layout:
  - `apps/core/` (infrastructure: base models, middleware, decorators,
    `APIResponse`, health-check) — kept.
  - `apps/accounts/` (identity) — absorbed `apps/tenants/`. `User`, `Role`,
    `Permission`, `Tenant` now all live here.
  - `apps/service/` (domain) — new app. Absorbed `apps/common/` and
    `apps/ingestion/`. Holds 7 domain models (`Subject`, `Class`,
    `ClassSubject`, `Document`, `ContentNode`, `Asset`, `ContentCrossRef`),
    the 10-file ingestion pipeline under `services/ingestion/`, and the
    `ingest_document` management command.
  - `apps/web/` (presentation) — new app. Absorbed `apps/school_admin/`
    plus the auth views from `apps/accounts/views/auth_views.py` plus the
    `home` / `dashboard_router` views from `apps/core/views.py`. Owns no
    models. Single `apps/web/urls.py` registers three sub-namespaces:
    `auth:`, `school_admin:`, `web:`.
- **2026-04-27 • clients** • Top-level `services/` package (which mixed
  Django app code with external clients) was split:
  - `clients/llm/` (was `services/ai/llm_service.py`)
  - `clients/embeddings/` (was `services/ai/embedding_service.py`)
  - `clients/vector_store/` (was `services/vector_store/client.py`)
  - `clients/storage/` (placeholder)
  - `services/ai/question_generator.py` was domain logic, moved to
    `apps/service/services/assessments/question_generator.py`.
- **2026-04-27 • cleanup** • Deleted empty stub apps (`analytics`,
  `assessments`, `goals`, `tutoring`, `monitoring`). Future logic for these
  features is tracked in `docs/todo.md` and will live as service modules
  under `apps/service/services/<feature>/`, not as separate Django apps.
- **2026-04-27 • migrations** • Wiped `db.sqlite3` plus all old migration
  files, re-ran `makemigrations` + `migrate` from scratch. New migration
  layout:
  - `accounts.0001_initial` (Permission, Role, Tenant, User)
  - `service.0001_initial` (Subject, Class, ClassSubject, Document,
    ContentNode, Asset, ContentCrossRef + indexes + unique_together).
- **2026-04-27 • routing** • New URL layout in `config/urls.py`:
  `/admin/`, `/auth/...` (`auth:`), `/school-admin/...` (`school_admin:`),
  `/health/` (`core:`), `/` & `/dashboard/` (`web:`). Templates updated:
  `core:home` → `web:home`, `core:dashboard` → `web:dashboard`. All other
  template URL refs (`auth:*`, `school_admin:*`, `core:health_check`)
  unchanged.
- **2026-04-27 • verification** • `python manage.py check` passes with 0
  issues. `python manage.py create_roles` re-seeds 4 roles + 20
  permissions. Dev server boots clean. Smoke-tested:
  `GET / → 200`, `GET /auth/login/ → 200`, `GET /health/ → 200` returns
  `{"status":"healthy"}`, `GET /dashboard/ → 302` (correctly redirects
  unauthenticated to login), `GET /school-admin/classes/ → 302`.

---

## Phase 1 — Foundation _(complete)_

### Project skeleton & config

- Django 4.2 project initialized as `config/`.
- Split settings: `config/settings/{base,development,production}.py`.
  Development uses SQLite, production uses PostgreSQL + WhiteNoise + Sentry +
  Redis cache.
- `config/urls.py` with role-based routing (`/auth/`, `/school-admin/`,
  `/admin/`, `/health/`).
- Three requirements files: `requirements/{base,development,production}.txt`.
- `.env.example`, `.gitignore`, `setup.bat`, `run.bat` at root.
- Logging configured to JSON via `python-json-logger` to `logs/app.log` plus
  console.

### `apps/core/` — infrastructure

- 4 abstract base models in `apps/core/models/base.py`: `TimestampedModel`,
  `TenantAwareModel`, `AuditModel(TimestampedModel)`, `SoftDeleteModel`.
- Middleware:
  - `TenantMiddleware` resolves tenant from subdomain or `request.user.tenant`
    and sets `request.tenant`.
  - `RequestLoggingMiddleware` logs every request with correlation ID.
  - `ExceptionHandlerMiddleware` catches uncaught exceptions and returns
    standardized error JSON.
- `APIResponse` utility (`apps/core/utils/response.py`) with `success`,
  `error`, `not_found`, `forbidden`, `unauthorized`, `validation_error`,
  `server_error`.
- Decorators: `@role_required(roles)`, `@tenant_required`,
  `@log_action(name)`, `@ajax_required`.
- Views: `home`, `dashboard_router` (role-aware redirect), `health_check`
  (JSON, checks DB).

### `apps/accounts/` — auth & RBAC

- Custom `User` (extends `AbstractUser` + `TimestampedModel`) with
  email-as-username, tenant FK, role FK, profile fields, JSON preferences.
  `UserManager` keyed on email.
- `Role` model (4 codes: `student`, `teacher`, `school_admin`, `system_admin`)
  with M2M `Permission` and hierarchy `level`.
- `Permission` model with code/name/category.
- `AuthService`: login (with remember-me), logout, password change, password
  reset initiation, email verification, IP capture.
- `RBACService`: permission checks, queryset filtering by role, tenant access
  control, user-management permissions, default role bootstrap.
- Views: login, logout, password change, password reset request.
- Management commands:
  - `create_roles` — seeds 4 roles + 20 permissions.
  - `create_system_admin` — interactive CLI to create a system admin user
    that has no Django admin access.
- Admin registrations for `User`, `Role`, `Permission`.
- 1 initial migration.

### `apps/tenants/` — multi-tenant

- `Tenant` model: name, slug (auto), domain, logo, primary_color, settings
  (JSON), subscription_tier (free/basic/premium/enterprise),
  subscription_expires, max_students, max_teachers, contact fields.
- `is_subscription_active`, `full_domain` properties; settings get/set
  helpers.
- Admin registration.
- 1 initial migration.
- _(Phase 0 plan: merge into `apps/accounts/` so identity is one app.)_

### `apps/common/` — shared academic models

- `Subject` (tenant-aware, code/name/color/icon).
- `Class` (tenant-aware, grade_level 1-12, section, academic_year, class_teacher
  FK, max_students; `student_count` and `is_full` properties).
- `ClassSubject` (subject ↔ class with teacher FK and JSON schedule).
- `Document` (tenant-aware + audit, file/title/file_type/file_size/subject FK/
  class_obj FK/status pending|processing|completed|failed).
- `FileUtils` for upload validation, MIME / size checks, unique filenames.
- Admin registrations.
- 2 migrations.
- _(Phase 0 plan: fold into `apps/service/models/`.)_

### `apps/ingestion/` — document pipeline (services done, no UI yet)

- Models: `ContentNode`, `Asset`, `ContentCrossRef` — with hierarchical parent
  links, node types (chapter / section / topic / definition / formula /
  example / exercise / summary / key_point), difficulty levels, page numbers,
  metadata JSON, embedding ids.
- Pipeline orchestrator (`IngestionPipeline.run(document_id)`) wiring 5
  stages: PDF render → TOC discovery + page calibration → chapter outlining +
  vision-LLM content structuring → image linking → storage with embeddings →
  cross-reference building.
- 10 service modules: `pdf_renderer`, `toc_discovery`, `page_calibration`,
  `chapter_outliner`, `content_structurer`, `image_linker`, `content_storage`,
  `cross_ref_builder`, `pipeline_orchestrator`, `latex_utils`.
- Math content enforced as LaTeX. Rolling summary used for context continuity
  across pages.
- Management command: `ingest_document <document_id> [--skip-vision]
  [--max-pages N] [--list] [--force]`.
- Admin registrations.
- 1 initial migration.
- _(Phase 0 plan: move services into `apps/service/services/ingestion/`,
  models into `apps/service/models/`.)_

### `apps/school_admin/` — school portal (template-only app)

- No models. Views consume User / Class / Subject / Document.
- 5 view modules: `class_views`, `subject_views`, `teacher_views`,
  `student_views`, `document_views` covering full CRUD plus subject
  assignment and active-toggle.
- 6 forms: `ClassForm`, `SubjectForm`, `ClassSubjectForm`,
  `TeacherInviteForm`, `StudentInviteForm`, `DocumentUploadForm`.
- Teacher / student invite generates 10-char password (letters + digits +
  `!@#$%`) and creates a User with the right role + tenant.
- All views guarded by `@role_required(['school_admin'])` and filter by
  `request.tenant`.
- Templates under `frontend/templates/school_admin/`: `classes/{list,detail}`,
  `subjects/list`, `teachers/list`, `students/list`, `documents/list`,
  `includes/sidebar_nav`.
- _(Phase 0 plan: move to `apps/web/views/school_admin/`.)_

### Top-level `services/` (external clients)

- `services/ai/llm_service.py` — `LLMService` against any OpenAI-compatible
  API. Methods: `generate(prompt, system, max_tokens, temperature)`,
  `generate_with_context(query, context_chunks, system_prompt)` returning
  `{answer, sources, model, timestamp}`.
- `services/ai/embedding_service.py` — `EmbeddingService` over
  sentence-transformers `all-MiniLM-L6-v2`, 384-dim. Singleton
  `get_embedding_service()`. Optional preload at startup via
  `services.apps.ServicesConfig.ready()`.
- `services/ai/question_generator.py` — stub.
- `services/vector_store/client.py` — `VectorStoreClient` over ChromaDB
  PersistentClient. Methods: `get_or_create_collection`, `add_documents`,
  `search`, `delete_documents`, `get_collection_stats`, `list_collections`,
  `delete_collection`. Tenant namespacing via `<tenant_id>_<name>`.
- `services/storage/` — empty stub for future S3/MinIO.
- _(Phase 0 plan: move all of this to top-level `clients/` (NOT a Django
  app), split per concern.)_

### Frontend

- 4 vanilla-JS utility classes in `frontend/static/js/core/`: `APIClient`
  (auto CSRF, returns `{success, ...}`), `Toast`, `FormHandler`, `Modal`.
- 4 CSS files: `core.css`, `dashboard.css`, `landing.css`,
  `school_admin.css`. CSS variables for theming.
- Templates (23 total):
  - `base/`: `base.html` (master), `dashboard_base.html` (sidebar wrapper),
    `home.html`, `landing.html`, `no_role.html`.
  - `components/`: `landing_navbar.html`, `navbar.html` (auth navbar with
    user dropdown), `footer.html`.
  - `auth/`: `login.html` (gradient design), `password_change.html`,
    `password_reset_request.html`.
  - `dashboards/`: `student_dashboard.html`, `teacher_dashboard.html`,
    `school_admin_dashboard.html`, `system_admin_dashboard.html`,
    `superadmin_dashboard.html`.
  - `school_admin/`: list/detail templates for classes, subjects, teachers,
    students, documents.

### Empty stub apps (placeholders only, slated for deletion)

- `apps/analytics/`, `apps/assessments/`, `apps/goals/`, `apps/tutoring/`,
  `apps/monitoring/` — folders contain only `apps.py`, `__init__.py`, empty
  `admin.py`. Deleted in Phase 0; future logic for these features will live
  inside `apps/service/services/<feature>/` instead of separate apps.

---

## Tally

- **Models in DB**: User, Role, Permission, Tenant, Subject, Class,
  ClassSubject, Document, ContentNode, Asset, ContentCrossRef = **11
  models** across 5 migrations.
- **Lines of Python**: ~3,500 (excluding migrations + templates + static).
- **Templates**: 23 HTML.
- **JS files**: 4 utility classes.
- **Management commands**: `create_roles`, `create_system_admin`,
  `ingest_document`.
- **External clients ready**: LLM (OpenAI-compatible), embeddings
  (sentence-transformers, 384-dim), vector store (ChromaDB persistent).
