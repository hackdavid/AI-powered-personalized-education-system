# EduAI Platform — Todo (phased backlog)

Source of truth for what comes next. Phases are roughly sequential but
items inside a phase can run in parallel. Mark items as `[x]` in this file
when done and add an entry to `progress.md`.

> **Plan revision (2026-04-27):** real ingestion (DRF + Celery + UI swap)
> moved to the END (Phase 6). Reason: it costs LLM credits per book and
> blocks every downstream feature on a paid pipeline. Replaced by a
> **synthetic data** Phase 1 that fills the existing tables with
> hand-authored, multi-tenant, multi-grade curriculum content (markdown +
> markdown tables, no images for now). All downstream phases (tutoring,
> assessments, analytics, goals) are then built end-to-end on free local
> embeddings + LLM-gated stubs, and real ingestion is flipped on at the
> end with no schema changes required.

---

## Phase 0 — Refactor & cleanup _(complete — 2026-04-27)_

All Phase 0 work landed in one pass. The repo went from 10 apps + 13
markdown files to 4 apps + 4 living docs. See `progress.md` for details.

- [x] Consolidate 13 root MD files + parent `IMPLEMENTATION_PLAN.md` /
      `overview.txt` into `docs/{project_aim,memory,progress,todo}.md`.
- [x] Replace root `README.md` with a thin pointer.
- [x] Build new 4-app skeleton: `apps/{core,accounts,service,web}` plus
      top-level `clients/{llm,embeddings,vector_store,storage}`.
- [x] Move `apps/tenants/models.py::Tenant` into `apps/accounts/models/`.
- [x] Move `apps/common/` + `apps/ingestion/` into `apps/service/`
      (models + services + management commands + admins).
- [x] Move `apps/school_admin/` into `apps/web/views/school_admin/` +
      `apps/web/forms.py` + `apps/web/urls.py`.
- [x] Move `apps/accounts/views/auth_views.py` into `apps/web/views/auth.py`.
- [x] Move `apps/core/views.py::home` and `dashboard_router` into
      `apps/web/views/public.py` and `apps/web/views/dashboards.py`.
      `health_check` stays in `apps/core/views.py`.
- [x] Move `services/ai/*` and `services/vector_store/` to top-level
      `clients/`. Move `question_generator.py` (domain logic) into
      `apps/service/services/assessments/`.
- [x] Delete 5 empty stub apps and old top-level `services/`.
- [x] Sweep all `.py`, `.html`, `.bat` imports/url refs to the new paths.
- [x] Update `config/settings/base.py::INSTALLED_APPS` and `config/urls.py`.
- [x] Reset `db.sqlite3` + all migrations. Run `makemigrations` + `migrate`
      + `create_roles` clean.
- [x] Smoke test: `python manage.py check` clean, server boots,
      `GET /` 200, `GET /auth/login/` 200, `GET /health/` 200,
      `GET /dashboard/` 302, `GET /school-admin/classes/` 302.

### 0.x Follow-up (not blocking)
- [ ] Recreate Django superuser locally: `python manage.py createsuperuser`.
- [ ] If tenant subdomain testing is needed, add an entry to `hosts` for
      `<slug>.localhost`.

---

## Phase 1 — Synthetic data + schema hardening _(complete — 2026-04-27)_

**Goal:** populate the existing schema with multi-tenant, multi-grade,
multi-subject curriculum content (markdown + markdown tables) so every
downstream feature can be built end-to-end without LLM cost. Real
ingestion is deferred to Phase 6 — no schema redesign needed there.

### 1.1 Schema hardening (single small migration)

- [x] `service.Document.file` → made `blank=True, null=True` (synthetic
      books have no PDF attached).
- [x] Added `service.Document.source_type = CharField(choices=[('pdf','PDF'),
      ('synthetic','Synthetic')], default='pdf')` + index on
      `(tenant, source_type)`.
- [x] Added `service.Document.SourceType` TextChoices enum.
- [x] Migration `service.0002_document_source_type_alter_document_file_and_more`
      generated and applied.
- [x] `apps/service/admin.py` exposes `source_type` in `DocumentAdmin`
      list_display + list_filter.

### 1.2 Synthetic content sources

- [x] Added `PyYAML` to `requirements/base.txt`.
- [x] `fixtures/synthetic_books/` directory created.
- [x] All 6 starter books authored:
      - [x] `math-grade-8.yaml` (algebra basics, geometry — table of operations, table of triangle types)
      - [x] `math-grade-9.yaml` (quadratics, intro trig — discriminant table, trig ratio table)
      - [x] `science-grade-8.yaml` (cells, Newton's laws — organelle table, Newton's laws table)
      - [x] `science-grade-9.yaml` (atoms, energy — periodic table category table, energy forms table)
      - [x] `english-grade-8.yaml` (parts of speech, sentences — pronoun-case table, sentence-types table)
      - [x] `english-grade-9.yaml` (literary devices, essays — figurative-device table)
- [x] Each book ships ≥1 markdown table.
- [x] Each book has 2 chapters × 2 sections × ~1–2 topics × 2–4 leaves.

### 1.3 Seeding service layer

- [x] `apps/service/services/seeding/__init__.py` exports the four
      public seed functions.
- [x] `apps/service/services/seeding/tenants.py` — `seed_tenants(slugs)`
      and `reset_tenant_synthetic_data(tenant)`.
- [x] `apps/service/services/seeding/users.py` — `seed_users(tenant)`
      (1 school_admin + 10 teachers + 80 students by default; idempotent
      on email; deterministic via `Faker.seed`).
- [x] `apps/service/services/seeding/classes.py` — `seed_subjects`,
      `seed_classes`, `seed_class_subjects`. Default subjects: MATH, SCI,
      ENG, HIST, GEO. Default grades: 8, 9. Default sections: A, B.
- [x] `apps/service/services/seeding/books.py` — `seed_books`,
      `discover_book_files`, `load_book_yaml`. Wipes + rebuilds the
      ContentNode tree per book on every run so the YAML is the source
      of truth.
- [x] `apps/service/services/seeding/submissions.py` — Phase 4 stub.
- [x] All seeders idempotent: `get_or_create` keyed on stable unique fields.

### 1.4 Management command

- [x] `apps/service/management/commands/seed_synthetic_data.py`
- [x] Flags implemented:
      - `--tenant <slug>` (repeatable; default: seed `springfield` and
        `riverside`)
      - `--reset` — delete synthetic Documents (and cascading nodes)
        scoped by tenant before seeding
      - `--books-only` / `--users-only` — partial reseed
      - `--with-embeddings` — runs sentence-transformers and upserts each
        ContentNode into ChromaDB (`<tenant_id>_curriculum`)
      - `--seed N` — deterministic RNG seed for `faker`
- [x] Concise per-step + final summary printed.

### 1.5 Verification

- [x] `python manage.py check` clean.
- [x] `python manage.py seed_synthetic_data --reset` produces:
      `tenants=2 users=+182 (1 SA + 10 T + 80 S per tenant)
      subjects=10 classes=8 class_subjects=40 books=12 chapters=24
      sections=38 topics=40 leaves=108 cross_refs=24`.
- [x] Tenant isolation smoke test passes (cross-tenant queryset returns
      0 rows for both directions).
- [x] Sample Document inspection: synthetic books have
      `source_type='synthetic'`, `status='completed'`, `file=None`.
- [x] Sample ContentNode tree inspection: chapter → section → topic →
      leaves with proper `parent` linkage and node_id paths
      (e.g. `ch1.s2.t1.l3`).
- [x] Integration tests at `apps/service/tests/test_seeding.py` —
      5 tests, all passing:
      - `test_full_seed_creates_expected_rows`
      - `test_seed_is_idempotent`
      - `test_tenant_isolation`
      - `test_book_yaml_files_discovered`
      - `test_content_node_tree_has_expected_types`

### 1.x Follow-up (not blocking)

- [ ] Browser smoke check: log in as `admin@springfield.test` /
      `Test@1234` (or the env-overridden `SEED_DEFAULT_PASSWORD`) and
      confirm `/school-admin/classes/`, `/school-admin/subjects/`,
      `/school-admin/documents/` render with seeded data and topic
      detail renders the markdown table.
- [ ] Promote `apps/service/tests/test_seeding.py` into an authoritative
      `tests/integration/` location once a project-level pytest config
      lands (Phase 7 production-readiness).

---

## Phase 2 — Tutoring (RAG chat) _(complete — 2026-04-29)_

Built end-to-end on synthetic data. LLM-gated branch confirmed via mocked
unit test; default offline answerer returns the top retrieved sources
verbatim with `model='stub'` so the chat UX is fully exercised without
paying for tokens. Rate-limiting deferred to Phase 7 per planning
decision.

- [x] Models in `apps/service/models/`: `TutoringSession` (tenant-aware,
      FK student, FK subject, title auto-derived, last_message_at indexed)
      and `ChatMessage` (FK session cascade, role student|assistant,
      content, retrieved_chunks JSON, model). Migration
      `service.0003_tutoringsession_chatmessage_and_more`.
- [x] `apps/service/services/tutoring/tutor_service.py::TutorService.
      answer_question(session, student, query, top_k=5)` returning
      `TutorAnswer` (user_message, assistant_message, sources, model).
      Internally retrieves top-k from `<tenant_id>_curriculum` via
      `CurriculumRetriever` and calls
      `clients.llm.LLMService.generate_with_context` when
      `OPENAI_API_KEY` is set; otherwise routes to `stub_answerer`.
      LLM exceptions fall back to the stub with a logged warning.
- [x] DRF `TutoringSessionViewSet` with all four originally planned routes
      plus list, destroy, and GET messages:
      - `POST   /api/v1/tutoring/sessions/`
      - `GET    /api/v1/tutoring/sessions/`
      - `GET    /api/v1/tutoring/sessions/<id>/`
      - `DELETE /api/v1/tutoring/sessions/<id>/` (archives)
      - `GET    /api/v1/tutoring/sessions/<id>/messages/`
      - `POST   /api/v1/tutoring/sessions/<id>/messages/`
      All wrap `APIResponse`. Cross-tenant access returns 404.
- [x] Web UI: `apps/web/views/student/chat.py::chat_view` +
      `frontend/templates/student/chat.html` +
      `frontend/static/css/student.css` +
      `frontend/static/js/student/chat.js`. Hydrates session list and
      messages via `APIClient`; renders citation chips; new-session
      modal; mobile-collapsing two-column layout.
- [x] Source-citation rendering: `[1]`, `[2]`, … in answer text are
      converted to clickable chips that toggle the corresponding source
      row (title, page, snippet) below the bubble. Sources reference
      `ContentNode` rows seeded in Phase 1.
- [ ] **Deferred:** rate-limit per student per minute — moved to Phase 7
      (production hardening). Cache infra not yet wired in dev.
- [x] Tests: 16 passing in `apps/service/tests/test_tutoring.py`
      covering service stub + real-LLM branches + tenant guard +
      view-level RBAC + message persistence. Whole `apps.service` test
      suite green at 21/21.

---

## Phase 3 — Assessments

**LLM-cost note:** ship manual question authoring first. AI question
generation is gated on `OPENAI_API_KEY`; a canned-generator stub returns
fixed sample questions per topic for dev so the teacher UI flow is
end-to-end testable.

- [ ] Models: `Assignment` (tenant-aware + audit, title, description, FK
      subject, FK class, FK created_by, due_date, total_marks),
      `Question` (FK assignment, question_text, type mcq|short|essay,
      options JSON, correct_answer, marks, order),
      `StudentAssignment` (FK assignment, FK student,
      status pending|in_progress|submitted|graded, submitted_at, score),
      `Answer` (FK student_assignment, FK question, answer_text,
      marks_awarded, feedback).
- [ ] Promote `clients.llm` + the existing `question_generator.py` stub to
      a real `apps/service/services/assessments/question_generator.py` —
      `generate_questions(topic, difficulty, count, question_type)`
      returning JSON list. Add a `StubQuestionGenerator` returning canned
      MCQs per topic (used when no API key).
- [ ] Auto-grading service for MCQ + short-answer (essay grading deferred).
- [ ] DRF endpoints for assignment CRUD + submit + grade.
- [ ] Teacher UI: create assignment (manual auth + AI-generated questions
      preview + edit), assignment list, submission review.
- [ ] Student UI: assignment list, take assignment (form), see graded
      results.

---

## Phase 4 — Analytics

- [ ] Extend `seed_synthetic_data` with `--with-submissions` flag:
      generates `StudentAssignment` + `Answer` rows with realistic score
      distributions (per-student bias, per-topic difficulty curve) so
      heatmaps have data to draw.
- [ ] `apps/service/services/analytics/heatmap.py`: per-class heatmap of
      `(student × assignment)` score percentages.
- [ ] Per-student dashboard: subject mastery, recent submissions, time
      spent in tutor.
- [ ] Per-class dashboard for teachers: heatmap, top struggles, completion
      rates.
- [ ] Per-school dashboard for school admin: usage, content coverage,
      teacher activity.
- [ ] DRF endpoints + chart-friendly JSON.
- [ ] Templates that render charts (use a tiny vendored library, e.g.
      Chart.js).

---

## Phase 5 — Goals & gamification

No LLM dependency for the core loop; LLM-assisted goal-to-task expansion
is opt-in.

- [ ] Models: `Goal` (tenant-aware, FK student, title, description,
      target_date, FK subject, status active|completed|abandoned,
      xp_reward), `Task` (FK goal, title, description, is_completed, order),
      `StudentProgress` (one-to-one student, total_xp, level, badges JSON).
- [ ] Services: goal-to-task expansion (LLM-assisted, gated by API key
      with a deterministic stub fallback), XP awarding rules, level-up
      calculation, badge unlocking.
- [ ] Student UI: "solo-leveling" style goal panel — goal + tasks + XP
      bar + recent badges.
- [ ] Notifications via Toast on level-up / badge unlock.

---

## Phase 6 — Real ingestion: API, async, UI _(deferred from old Phase 1)_

The pipeline already exists as services + a CLI. Turning it into a
feature is the LAST thing we ship — by this point the rest of the system
runs end-to-end on synthetic data and switching a `Document.source_type`
from `synthetic` to `pdf` is the only difference.

- [ ] DRF `Document` serializer + viewset under
      `apps/service/api/documents.py`. Endpoints: `POST /api/v1/documents/`,
      `GET /api/v1/documents/{id}/`, `POST /api/v1/documents/{id}/ingest/`,
      `GET /api/v1/documents/{id}/status/`.
- [ ] Wire `IngestionPipeline` into a Celery task
      `service.tasks.ingestion.run_ingestion(document_id)` (sync fallback
      for dev when Redis is absent — gate on `CELERY_BROKER_URL` env).
- [ ] Update `Document.status` transitions:
      `pending → processing → completed | failed`. Save `error_message` on
      failure.
- [ ] Progress webhook / status polling: keep it simple for now, expose
      `status` + percent on the GET endpoint.
- [ ] School-admin upload UI: switch
      `apps/web/views/school_admin/document_views.py::document_upload` to
      call the API endpoint via `APIClient` and show a Toast on success.
- [ ] Ingestion list UI shows live status (poll every 3s while
      `processing`).
- [ ] Add health-check probe for vector store + LLM client (extend
      `apps/core/views.py::health_check`).
- [ ] Verify: a real PDF upload produces `ContentNode` rows that look
      structurally identical to the synthetic ones (same node_types,
      same hierarchy, same markdown style). If not, fix the pipeline —
      not the schema.

---

## Phase 7 — Production readiness

- [ ] Celery + Redis fully wired (or chosen alternative). Production
      `.env` documents the broker URL.
- [ ] S3/MinIO storage backend in `clients/storage/` with `default_storage`
      override for prod.
- [ ] Test suite under `tests/`:
  - Unit: `apps/core` base models + decorators + APIResponse,
    `apps/accounts/services/`, ingestion services (mocked LLM),
    tutoring service, seeding services.
  - Integration: ingestion happy path on a small sample PDF, RAG answer
    grounding, assignment lifecycle, seed idempotency.
  - E2E: login → role-based dashboard → key flow per role.
- [ ] CI workflow: lint (`black --check`, `flake8`), test
      (`pytest`), coverage gate.
- [ ] Sentry hookup verified in production settings.
- [ ] Database backup / restore scripts under `scripts/`.

---

## Backlog / nice-to-haves (not phased)

- [ ] Tenant subdomain routing (`<slug>.platform.com`) end-to-end.
- [ ] Tenant branding (logo + primary color) reflected in templates.
- [ ] Email backend hookup (registration, password reset, assignment
      notifications).
- [ ] OpenAPI / Swagger docs at `/api/docs/` once REST layer lands.
- [ ] Per-subject vector collections instead of one big `_curriculum`.
- [ ] Adaptive difficulty in question generation based on student history.
- [ ] Mobile-friendly polish on dashboards.
- [ ] Replace ChromaDB with pgvector when scale demands it.
- [ ] Replace sentence-transformers with a hosted embedding API for
      production accuracy gains.
- [ ] Extend synthetic books to grades 6, 7, 10, 11, 12 once Phase 1+2
      land and we know the RAG quality bar.
- [ ] Synthetic data: add `Asset` rows for select tables (vs inline
      markdown) once a feature actually needs structured table data.
- [ ] Synthetic data: image generation for figures (currently skipped).
