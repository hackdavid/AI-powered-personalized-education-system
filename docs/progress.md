# EduAI Platform — Progress

Append-only ledger of shipped work. Newest entries at the top. Each entry:
**date** • **scope** • **what** • **where**.

---

## Phase 3D — Render deployment plumbing _(complete)_

**Why:** the platform was running locally only. To get it in front of
real users (or evaluators) we need a production host with autoDeploy
from the main branch. Render fits — Docker runtime, free GitHub
integration, you have credits.

- **2026-04-30 • Dockerfile** • Single-stage `python:3.12-slim` image.
  Installs `requirements.txt`, runs `collectstatic` at build time
  (with placeholder env so Django boots without a real DB), opens a
  writable `logs/` directory, exposes 8000 (Render injects `$PORT`).
  CMD runs Gunicorn with 2 sync workers, 60s timeout, access/error
  logs to stdout. ~280 MB final image.
- **2026-04-30 • .dockerignore** • Excludes `.git`, `db.sqlite3`,
  `chroma_data/` (legacy), `logs/`, `staticfiles/`, `.env*` (except
  `.env.example` siblings), `venv/`, `docs/` — keeps the build context
  small and prevents leaking developer secrets into image layers.
- **2026-04-30 • render.yaml** • Declarative Render Blueprint. Web
  service, Docker runtime, Starter plan, Frankfurt region (close to
  Supabase eu-west-1), `autoDeploy: true` on `main`. Sets
  `healthCheckPath: /health/` and a `preDeployCommand: python
  manage.py migrate --noinput` so migrations run BEFORE traffic
  switches to the new container. `envVars` block declares 9 vars:
  - `DJANGO_SECRET_KEY` (`generateValue: true` — Render auto-generates)
  - `DATABASE_URL`, `EMBEDDER_API_KEY` (`sync: false` — admin pastes
    these into Render dashboard manually; never committed)
  - 6 public defaults (`DJANGO_DEBUG=False`, allowed hosts, embedder
    URL, etc.)
- **2026-04-30 • settings.py tweaks for Render**:
  - `RENDER_EXTERNAL_HOSTNAME` (auto-injected by Render at runtime) is
    appended to `ALLOWED_HOSTS` if present, so a fresh deploy doesn't
    get blocked by Django's host-validation middleware.
  - `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')`
    added to the prod-only block. Render terminates TLS in front of
    the container; without this the `SECURE_SSL_REDIRECT=True` setting
    bounces the request infinitely.
- **2026-04-30 • health endpoint audit** • `apps/core/views.py::
  health_check` already does `SELECT 1` against the DB and returns
  `200 healthy` / `503 unhealthy` with a `checks` dict. No changes
  needed — Render uses it as the readiness probe out of the box.
- **2026-04-30 • docs** • New `docs/deployment.md` — full
  GitHub-to-Render walkthrough: blueprint creation, secret env-var
  setup, first deploy, day-to-day workflow (auto-deploy on push,
  one-off shell commands, AppSetting hot-edit + restart, rolling back
  via the Deploys tab). Notes on free tier auto-suspend, memory
  pressure, transaction-pool migration caveats. `docs/memory.md` §1
  (project shape) lists the four new infra files; §2 (tech stack)
  adds a "Deploy target: Render (Docker, autoDeploy)" row; §13
  (useful pointers) gets a one-line deploy summary.

### What's needed to actually go live

- [ ] Push the repo to GitHub (Render only deploys from a remote)
- [ ] In Render dashboard: New → Blueprint → connect repo
- [ ] Render reads `render.yaml`, asks for two secrets:
   - `DATABASE_URL` — the Supabase transaction-pooler URL (port 6543)
   - `EMBEDDER_API_KEY` — the HuggingFace Space token
- [ ] Manual Deploy → first build (~3–5 min) → Render swaps traffic
- [ ] `curl https://<service>.onrender.com/health/` → `{"status":"healthy"}`

After that, every `git push origin main` triggers a fresh deploy.

### Stayed in offline mode

`OPENAI_API_KEY` AppSetting row stays inactive on Supabase — the live
service runs the stub answerer with real pgvector retrieval. Zero LLM
spend in production. Flip it on later via
`/admin/core/appsetting/` + restart the Render service.

---

## Phase 3C — ChromaDB removed, onboarding examples added _(complete)_

**Why:** pgvector on Supabase is now doing all the vector work — time to
delete the dead `chromadb` path and leave the repo with a clean,
easy-to-follow onboarding story for new teammates.

- **2026-04-30 • deps** • Dropped `chromadb` from `requirements.txt`.
  Net effect: a fresh `pip install -r requirements.txt` no longer
  pulls in `onnxruntime`, `hnswlib`, `opentelemetry-*`, and the other
  ~30 transitive deps Chroma brought along.
- **2026-04-30 • settings** •
  - `config/settings.py` — `VECTOR_STORE_TYPE` default flipped from
    `chromadb` → `pgvector`. `CHROMADB_PERSIST_DIR` setting removed
    entirely.
  - `.env.example` — matching cleanup.
  - `apps/core/management/commands/bootstrap_app_settings.py` —
    `VECTOR_STORE_TYPE` description updated to "currently only
    pgvector".
  - `apps/core/tests/test_app_setting.py` — bootstrap override uses
    `VECTOR_STORE_TYPE='pgvector'`.
  - On Supabase, updated the existing `AppSetting` row for
    `VECTOR_STORE_TYPE` from `'chromadb'` to `'pgvector'` in place.
- **2026-04-30 • docs** •
  - `docs/memory.md` — §1 (project shape) drops the `chroma_data/`
    line; §2 (tech stack) vector-store row now says pgvector on
    Supabase; §8 (env vars) removes the `CHROMADB_PERSIST_DIR` row
    and updates `VECTOR_STORE_TYPE`; §10 (ingestion pipeline) now
    reads "upsert ContentEmbedding rows into Supabase pgvector"; §12
    (things NOT to do) mentions `pgvector` / `requests` /
    `sentence_transformers` instead of `chromadb`.
  - No code imports left referencing `chromadb` — confirmed via
    `grep -r 'import chromadb'` on the whole repo.
- **2026-04-30 • onboarding examples** • Two new example files so
  contributors don't have to guess:
  - `.env.local.example` — **minimal** env for local dev. Only three
    values to fill (`DJANGO_SECRET_KEY`, `DJANGO_DEBUG=True`,
    `DATABASE_URL`). Contrasts with the full `.env.example` which
    documents every optional prod flag.
  - `docs/admin_setup.md` — admin-side checklist: every AppSetting
    key, what value to paste, which are safe to leave inactive, and
    a step-by-step "flip on real LLM later" sequence. Explicitly
    documents that the happy default is **offline mode** (stub
    tutor, no OpenAI bill).
- **2026-04-30 • offline mode locked in** • `OPENAI_API_KEY` row on
  Supabase stays inactive. Tutor keeps using the stub answerer that
  formats retrieved chunks directly. Real grounded retrieval is
  happening — you just get the sources as-is instead of a paragraph
  of natural language. Zero LLM spend.
- **2026-04-30 • verification** •
  - `python manage.py check` — clean
  - `grep -r chromadb eduai_platform/` — only docs + comments remain
  - `python manage.py test apps` — **63/63 passing**
  - `AppSetting` row count on Supabase: 10 total, 8 active (same as
    before)

### What the repo looks like now

```
eduai_platform/
├── manage.py
├── requirements.txt              # SINGLE file, no torch, no chromadb
├── .env.example                  # full reference (every optional flag)
├── .env.local.example            # ← NEW: 3-line minimum for local dev
├── config/
│   └── settings.py               # single file, DEBUG-toggled
├── apps/
│   ├── core/                     # + AppSetting + bootstrap command
│   ├── accounts/
│   ├── service/                  # + ContentEmbedding + pgvector client
│   └── web/
├── clients/                      # llm, embeddings, vector_store (pgvector)
├── docs/
│   ├── project_aim.md
│   ├── memory.md
│   ├── progress.md
│   ├── todo.md
│   └── admin_setup.md            # ← NEW: AppSetting configuration guide
└── (no more chroma_data/)
```

### What a brand-new teammate does now

```bash
git clone <repo>
pip install -r requirements.txt
cp .env.local.example .env
#  paste DJANGO_SECRET_KEY + the shared DATABASE_URL
python manage.py runserver
```

No migrations, no seed, no API keys, no torch, no Chroma, no `chroma_data/`.
Login as a seeded demo account (see `docs/admin_setup.md` for the list)
and the RAG tutor works against shared Supabase pgvector in **offline
mode** (stub answerer, real retrieval).

---

## Phase 3B — pgvector replaces ChromaDB _(complete)_

**Why:** embeddings lived in a per-laptop `chroma_data/` directory which
meant every team-mate had to re-embed. Moving them into Supabase
Postgres via the `pgvector` extension makes them shared, indexed, and
backed-up with the rest of the ORM data. Drops one external dependency
and one per-developer install gotcha.

- **2026-04-29 • schema** • New model
  `apps/service/models/embedding.py::ContentEmbedding`. Columns:
  `tenant` FK, `content_node` FK (cascade), `embedding`
  `VectorField(384)`, `model_name` (varchar), `embedding_id` (legacy
  string id kept for debugging). Unique key `(content_node, model_name)`
  so one node can host multiple model versions later. Indexes:
  `(tenant, model_name)` btree.
- **2026-04-29 • migration** • `apps/service/migrations/0004_contentembedding.py`:
  - `pgvector.django.VectorExtension()` — idempotent
    `CREATE EXTENSION IF NOT EXISTS vector` (no-op on SQLite).
  - `CreateModel(ContentEmbedding, …)`.
  - `migrations.RunPython(create_hnsw_index_on_postgres,
    drop_hnsw_index_on_postgres)` — raw SQL for the HNSW cosine index
    guarded on `connection.vendor == 'postgresql'`. SQLite test DBs
    skip this silently so `manage.py test apps` works without
    Postgres.
  Index spec: `USING hnsw (embedding vector_cosine_ops) WITH
  (m = 16, ef_construction = 64)` — pgvector defaults, good for our
  ~10K-vectors scale.
- **2026-04-29 • client rewrite** •
  `clients/vector_store/client.py::VectorStoreClient` reshaped around
  pgvector. Public surface **unchanged** — same method signatures as
  the old ChromaDB client so `CurriculumRetriever`, `ContentStorage`,
  and `seed_synthetic_data._embed_tenant_nodes` all keep working
  untouched:
  - `get_or_create_collection(tenant_id, name)` — returns a thin
    `_Collection(tenant_id, name)` routing handle. No physical
    collection in pgvector; it's just a WHERE clause.
  - `add_documents(collection, documents, metadatas, ids)` — bulk
    embeds via the remote HF Space, then `bulk_create`s
    `ContentEmbedding` rows. Uses `(tenant, content_node, model_name)`
    as upsert key (delete-then-insert).
  - `search(collection, query, top_k)` — embeds query, ranks by
    `pgvector.django.CosineDistance`, returns the same
    `{text, metadata, score}` dicts as Chroma did. `score = 1 - cosine_distance`.
  - `delete_documents`, `list_collections`, `delete_collection`,
    `get_collection_stats` — implemented for parity.
- **2026-04-29 • embeddings populated** •
  `python manage.py seed_synthetic_data --reset --with-embeddings
  --books-only` against Supabase generated 148 `ContentEmbedding`
  rows (74 per tenant × 2 tenants). Each is 384-dim, L2-normalised,
  cosine-searchable via HNSW.
- **2026-04-29 • smoke** • Logged in as
  `william.king.79@springfield.test` (seeded grade-9 student), asked
  *"What is a quadratic equation and how do I use the discriminant?"*
  through the chat UI. Tutor returned 5 grounded chunks pulled
  straight from Supabase pgvector:
  ```
  [1] ch1.s1.t1      Standard form of a quadratic        score=0.79
  [2] ch1.s1.t1.l1   Quadratic equation                  score=0.61
  [3] ch1.s2.t1      Solving with the quadratic formula  score=0.57
  [4] ch1.s2.t1.l1   Quadratic formula                   score=0.53
  [5] ch1.s2.t1.l4   Practice 1                          score=0.47
  ```
  Stub answerer formatted them into the assistant message (no
  `OPENAI_API_KEY` active yet — switching that flag in admin will
  instantly produce real LLM answers grounded in these same chunks).
- **2026-04-29 • tests** •
  `apps/service/tests/test_pgvector_client.py` — 17 passing tests
  covering:
  - `_Collection` routing (tenant stringification, delete shim,
    count/peek)
  - `add_documents`: happy path, empty batch short-circuit, skip
    unknown nodes, dimension-mismatch error, re-embedding replaces
    existing row, tenant isolation (other tenant's rows untouched)
  - `search`: empty query short-circuit, embed_text called,
    `CosineDistance` invoked with correct args
  - Admin helpers: `delete_documents`, `list_collections`,
    `delete_collection`, `get_collection_stats`
  Tests use SQLite with `CosineDistance` mocked (no real vector math
  needed). Whole `apps` suite: **63/63 passing** (5 seeding + 16
  tutoring + 13 remote-embedder + 12 AppSetting + **17 pgvector**).

### What this means for retrieval

Before:

```
query → embed → chromadb PersistentClient on laptop disk → top-k hits
```

After:

```
query → embed via HF Space → Supabase pgvector HNSW search → top-k hits
                                                ↑
                                      shared across every dev machine
```

A teammate on a clean Windows box now needs zero vector-store setup —
no `chroma_data/` directory, no torch, no per-dev seed — they just
point at the shared `DATABASE_URL` and retrieval works.

### Still to do (Phase 3C — cleanup)

- Delete `chroma_data/` directory from repo root (already gitignored)
- Drop `chromadb` from `requirements.txt`
- Update `docs/memory.md` §10 (ingestion pipeline still mentions Chroma)
- Verify nothing else imports from `chromadb` (run a final grep + tests)

---

## Phase 3A — Shared Postgres on Supabase _(complete)_

**Why:** per-laptop SQLite meant every teammate re-ran migrations +
`seed_synthetic_data` on their own machine, and demo data drifted. One
shared Supabase Postgres ends that.

- **2026-04-29 • connection** • Supabase project at
  `db.vihkdpqvcruuvrgajdvv.supabase.co`. Direct host (`db.<ref>...`) is
  **IPv6-only** and blocked on the dev Windows machine — classic
  gotcha. Switched to the **session-mode transaction pooler**
  (`aws-0-eu-west-1.pooler.supabase.com:5432`, user
  `postgres.<project-ref>`), which is IPv4 and works on any OS.
  Documented in `.env.example` and memory.md as the default.
- **2026-04-29 • schema** • Ran all seven existing migrations against
  the fresh Supabase DB:
  - `contenttypes`, `auth`, `sessions`, `admin` (Django built-in)
  - `accounts.0001_initial` (User, Role, Permission, Tenant)
  - `service.0001_initial` → `.0003_tutoringsession_chatmessage_and_more`
  - `core.0001_initial` (AppSetting)
  Target Postgres version: 17.6 on aarch64-linux. No migration tweaks
  needed — the schema ported cleanly from SQLite.
- **2026-04-29 • identity** • `create_roles` seeded 4 roles + 20
  permissions (Student/Teacher/SchoolAdmin/SystemAdmin).
- **2026-04-29 • settings** • `bootstrap_app_settings --include-secrets`
  populated 10 `AppSetting` rows on Supabase — 8 active (URL-style
  settings + EMBEDDER_API_KEY), 2 inactive (`OPENAI_API_KEY`,
  `ANTHROPIC_API_KEY` left blank for the admin to fill in).
- **2026-04-29 • curriculum** • `seed_synthetic_data --reset` landed
  the full demo dataset on Supabase in one shot:
  ```
  tenants=2           (springfield, riverside)
  users=+182          (2 school_admins + 20 teachers + 160 students)
  subjects=10  classes=8  class_subjects=40
  books=12  chapters=24  sections=38  topics=40  leaves=108  cross_refs=24
  ```
  Documents total = 12 synthetic books. ContentNodes total = 210.
- **2026-04-29 • smoke** • Verified end-to-end against the shared DB:
  ```
  POST /auth/login/  (admin@springfield.test)      → 302 → /dashboard/
  GET  /dashboard/                                  → 200, 28 KB
  GET  /school-admin/classes/                       → 200, 4 classes rendered
  GET  /school-admin/students/                      → 200, 81 @springfield.test rows (80 students + admin)
  GET  /school-admin/documents/                     → 200, 6 synthetic books visible
  GET  /health/                                     → 200
  ```
- **2026-04-29 • gotcha fix** • `DJANGO_DEBUG=True` is now required
  in `.env` for local dev (default is `False` so production security
  headers don't surprise-enable on a team-mate's laptop). Without it,
  `SECURE_SSL_REDIRECT=True` sends every HTTP request to HTTPS and
  `runserver` breaks. Added it to the user's `.env` and the example.

### What this unlocks for the team

A new contributor does:

```bash
git clone <repo>
pip install -r requirements.txt
cp .env.example .env
#  fill in DJANGO_SECRET_KEY + DJANGO_DEBUG=True + the shared DATABASE_URL
python manage.py runserver
```

No `migrate`, no `seed`, no `create_roles`. The shared Supabase DB is
already seeded. They log in with any of the 182 demo accounts (e.g.
`admin@springfield.test` / `Test@1234`) and they're running.

### Still to do in Phase 3

- **B (next)** — replace ChromaDB with pgvector. New
  `ContentEmbedding` model + HNSW index; rewrite `PgVectorClient`;
  seed embeddings directly into Supabase. Drops the `chromadb`
  dependency entirely.
- **C** — cleanup: delete `chroma_data/`, drop `chromadb` from
  requirements, update memory.md tech-stack row.

---

## Phase 2.7 — Config + requirements simplified to single files _(complete)_

**Why:** three settings modules and three requirements files made the
onboarding flow noisier than it needed to be for a team our size.
Single file per concern; env-var switches for dev vs prod behaviour.

- **2026-04-29 • settings** • `config/settings/{__init__,base,development,production}.py`
  collapsed into one `config/settings.py`. All env-specific behaviour is
  driven by `DJANGO_DEBUG` or optional URL env vars (`DATABASE_URL`,
  `REDIS_URL`, `SENTRY_DSN`, `EMAIL_HOST`). Nothing from the old
  production.py was lost — it now lives behind `if not DEBUG:` blocks.
- **2026-04-29 • database** • Added `dj-database-url` dependency.
  Resolution order: `DATABASE_URL` (Supabase/Postgres) → SQLite if
  `DEBUG=True` → refuse to boot if neither. Connection options include
  `conn_max_age=600` + `conn_health_checks=True` out of the box.
- **2026-04-29 • requirements** • `requirements/{base,development,production,embeddings-local}.txt`
  → single `requirements.txt`. Dev tooling (pytest / black / flake8 /
  django-extensions) lives in the same file. `sentence-transformers`
  stays commented out at the bottom as an opt-in fallback (the remote
  embedder Space is the default). `chromadb` still in; flips out in
  Phase 3.
- **2026-04-29 • module paths** • `manage.py`, `config/wsgi.py`,
  `config/asgi.py` all now point at `config.settings` (not
  `config.settings.development`).
- **2026-04-29 • scripts + docs** • `setup.bat` installs
  `requirements.txt` (was `requirements\development.txt`). `.env.example`
  rewritten to match the new single file, grouped by concern, with
  `DATABASE_URL` documented and sensitive keys intentionally left blank.
  `docs/memory.md` §1 project shape + §8 env vars + §11 run commands
  updated. `README.md` quickstart now references the single file.
- **2026-04-29 • verification** • `python manage.py check` clean with and
  without `DATABASE_URL` set. Full test suite still green:
  `DJANGO_DEBUG=True DATABASE_URL= python manage.py test apps` →
  **46/46 passing** (5 seeding + 16 tutoring + 13 remote-embedder +
  12 AppSetting). Pure refactor, zero behaviour change.

### What this changes for a new teammate

```
git clone <repo>
pip install -r requirements.txt      # SINGLE file, no -r development.txt
cp .env.example .env                 # fill in DJANGO_SECRET_KEY + DATABASE_URL
python manage.py migrate
python manage.py runserver
```

No more "which requirements file?" / "which settings module?" questions.

---

## Phase 2.6 — Admin-editable runtime settings (`AppSetting`) _(complete)_

**Why:** API keys (`OPENAI_API_KEY`, `EMBEDDER_API_KEY`, …) need to live
somewhere that's editable by one trusted admin without sharing the value
into every team-mate's `.env`. `.env` files are also annoying to keep in
sync across machines.

- **2026-04-29 • model** • New `apps/core/models/app_setting.py::AppSetting`
  (extends `AuditModel`). Columns: `key`, `value` (TextField), `category`
  (TextChoices: llm / embedding / vector_store / tutoring / platform /
  other), `description`, `is_secret`, `is_active`. Single composite index
  on `(is_active, category)`. `masked_value` property: full text for
  non-secrets, `••••<last 4>` for secrets.
- **2026-04-29 • startup hook** • `apps/core/apps.py::CoreConfig.ready()`
  now reads every `AppSetting` row where `is_active=True` and applies
  it via `setattr(django.conf.settings, key, value)`. Wrapped in
  `OperationalError`/`ProgrammingError` try/except so first migration
  doesn't crash. Skips `makemigrations`/`migrate`/etc. by inspecting
  `sys.argv[1]` to avoid the table-not-yet-there race. Suppresses
  Django's cosmetic "Accessing the database during app initialization
  is discouraged" RuntimeWarning since the warning is the documented
  pattern for this use case.
- **2026-04-29 • admin** • New `apps/core/admin.py::AppSettingAdmin`.
  Changelist masks secrets in the `value` column (only last 4 chars).
  Detail view shows full value (admin is staff-only). `save_model`
  auto-stamps `created_by` / `updated_by` from `request.user`. Fieldset
  description tells the admin "Changes don't take effect until the
  server restarts" so the UX expectation is in the form itself.
- **2026-04-29 • bootstrap CLI** • New management command
  `bootstrap_app_settings` (`apps/core/management/commands/`). Idempotent:
  scans a `REGISTRY` of 10 known overridable keys, creates a row per key
  copying the current `.env` value (public keys only by default; pass
  `--include-secrets` to also copy keys). Re-running NEVER overwrites a
  curated value. `--reset` deletes everything (with `yes` confirmation).
  Secrets without a value land as `is_active=False` so admin notices
  them in the changelist.
- **2026-04-29 • tests** • New `apps/core/tests/test_app_setting.py` —
  12 passing tests:
  - 5 model: `__str__`, mask semantics for empty / short-secret /
    long-secret / non-secret values
  - 4 hand-off: active row overrides settings, inactive row leaves
    settings alone, edit-then-reapply mirrors restart UX, multiple
    active rows all propagate
  - 3 bootstrap: first-run creates expected rows + leaves secrets
    blank/inactive, `--include-secrets` copies keys, re-run is
    idempotent (does not overwrite admin-curated values)
- **2026-04-29 • verification** • Server start now logs:
  `INFO apps Applied 8 AppSetting override(s) to django.conf.settings.`
  End-to-end smoke (in shell):
  ```
  >>> AppSetting.objects.get(key='OPENAI_BASE_URL').value = 'https://custom-llm.example.com/v1'
  >>> AppSetting.objects.get(key='OPENAI_BASE_URL').save()
  >>> AppSetting.apply_to_settings()    # what ready() does on restart
  >>> settings.OPENAI_BASE_URL          # 'https://custom-llm.example.com/v1' ✓
  ```
  All `apps.*` tests still green: 5 seeding + 16 tutoring + 13 remote
  embeddings + 12 AppSetting = **46 passing**.

### What this changes for the team

- New developer flow: `git clone → pip install → cp .env.example .env`
  with `DJANGO_SECRET_KEY` only → `python manage.py migrate` →
  `python manage.py runserver`. They never see API keys.
- Daud (or whichever admin) edits values at `/admin/core/appsetting/`
  and restarts the server. `.env` files on team-mates' machines never
  need updating.
- Audit trail: every save records `updated_by` + `updated_at` in the row.

### Not yet (deliberately)

- **No live reflection.** Changes apply on next restart, not instantly.
  Acceptable trade-off for simplicity; revisit if multi-worker
  production needs faster propagation.
- **No tenant scoping.** Settings are global. Per-tenant overrides can
  land later as a nullable `tenant` FK without breaking anything (NULL
  = global).
- **No encryption-at-rest.** Plaintext in DB. The DB itself is
  access-controlled and Supabase will be access-controlled. We can
  switch to `EncryptedTextField` later via one migration.

---

## Phase 2.5 — Embeddings externalised to HuggingFace Space _(complete)_

**Why:** `sentence-transformers` requires `torch`, which is the most
common day-1 install failure on Windows + Conda. The whole team kept
hitting the same DLL-load wall. Solution: move the embedder behind an
HTTP boundary so the platform repo no longer needs ML deps.

- **2026-04-29 • new repo** • Sibling repo `eduai-embedder/` (lives at
  `code_base/eduai-embedder/text-embding-model/`, separate git, pushed
  to HF Space `huggingface.co/spaces/ibrahimdaud/text-embding-model`).
  ~80-line FastAPI app with three routes (`GET /health`,
  `POST /embed`, `POST /embed_one`), Dockerfile that pre-downloads
  `all-MiniLM-L6-v2` at build time, `X-API-Key` auth via Space secret,
  pinned dependencies. CPU `cpu-basic` Space, free tier, 16 GB RAM.
- **2026-04-29 • clients refactor** • `clients/embeddings/` is now a
  provider-aware factory:
  - `local_service.py` — renamed from `service.py`. Class
    `LocalEmbeddingService` (alias `EmbeddingService` retained for
    back-compat). Lazy-loads sentence-transformers on first call so
    forgetting `init_model()` no longer crashes.
  - `remote_client.py` — new. `RemoteEmbeddingService` matches the
    local API exactly (`embed_text`, `embed_batch`,
    `get_embedding_dimension`, `model_name`). Uses `requests.Session`
    with sticky `X-API-Key` header, retries on 408/429/5xx with
    0.5 s/1 s/2 s exponential backoff (3 attempts), 30 s timeout
    (covers HF Space cold start), raises `EmbeddingClientError` on
    permanent failure. Caches `model_name` and `dim` after first
    successful call so they're free forever after.
  - `__init__.py` — factory keyed on `settings.EMBEDDING_PROVIDER`
    (`remote` default, `local` fallback). Re-exports
    `get_embedding_service()` and `init_model()` so every existing
    caller (`VectorStoreClient`, `ContentStorage`, the seeding
    command) stays unchanged.
- **2026-04-29 • settings + env** • `config/settings/base.py` reads
  three new vars:
  - `EMBEDDING_PROVIDER` (default `remote`)
  - `EMBEDDER_API_URL` (required when provider=remote)
  - `EMBEDDER_API_KEY` (matches the Space secret)
  `.env.example` documents them with comments explaining the swap.
- **2026-04-29 • requirements** • `sentence-transformers` moved out of
  `requirements/base.txt` into a new `requirements/embeddings-local.txt`
  optional extra (which `-r base.txt` so it's a strict superset).
  Default install no longer pulls torch. `requests` is now in `base.txt`
  (was already transitively present). Net: `pip install -r
  requirements/development.txt` succeeds cleanly on Windows + Conda.
- **2026-04-29 • tests** • New `apps/service/tests/test_embeddings_remote.py`
  with 13 passing tests using `requests.Session.request` mocks (no
  network, no torch). Covers happy paths (`embed_text`, `embed_batch`,
  empty batch short-circuit, metadata caching), auth failures
  (401/403 without retry), retries (503 → 200, persistent 5xx exhausts,
  ConnectionError exhausts), missing-config errors, factory routing.
  All `apps.service` tests now: 5 seeding + 16 tutoring + 13 remote
  embeddings = **34 passing**.
- **2026-04-29 • verification** • End-to-end against the live Space:
  ```
  >>> svc = get_embedding_service()
  >>> type(svc).__name__   # 'RemoteEmbeddingService'
  >>> svc.model_name        # 'all-MiniLM-L6-v2'
  >>> svc.get_embedding_dimension()   # 384
  >>> v = svc.embed_text("What is a quadratic equation?")
  >>> sum(x*x for x in v)**0.5   # 1.0 (L2-normalised)
  ```
  Semantic check across 3 texts:
  `cos(similar Q1↔Q2) = 0.829`, `cos(unrelated Q1↔Q3) = 0.082`. Quality
  unchanged from running locally.

### Tally update

- **Repos in workspace**: 1 → **2** (added sibling `eduai-embedder`).
- **Lines of Python (eduai_platform)**: +~250 (`remote_client.py` +
  `test_embeddings_remote.py`).
- **Default `pip install` size**: dropped torch (~800 MB) + transitive
  CUDA stubs.
- **Tests**: 21 → **34** passing.

---

## Phase 2 — Tutoring (RAG chat) _(complete)_

- **2026-04-29 • models** • Two new domain models in
  `apps/service/models/tutoring.py`:
  - `TutoringSession(TenantAwareModel, TimestampedModel)` — `student` FK,
    optional `subject` FK, `title` (auto-derived from first user question),
    `is_active`, `last_message_at` (db_index). Composite index
    `(tenant, student, -last_message_at)`.
  - `ChatMessage(TimestampedModel)` — `session` FK (cascade), `role`
    (`student | assistant`), `content`, `retrieved_chunks` JSONField (per-hit
    `{node_id, document_id, title, snippet, score, page_number, ...}`),
    `model` (e.g. `gpt-4`, `stub`). Index `(session, created_at)`.
  - `apps/service/admin.py` registers both. `apps/service/models/__init__.py`
    re-exports the new symbols.
  - Migration: `service.0003_tutoringsession_chatmessage_and_more`.
- **2026-04-29 • services** • New service package
  `apps/service/services/tutoring/`:
  - `prompts.py` — `TUTOR_SYSTEM_PROMPT` + `build_system_prompt(grade_level)`
    that calibrates tone for younger / older students.
  - `retriever.py::CurriculumRetriever` — thin wrapper over
    `clients.vector_store.VectorStoreClient.search` against
    `<tenant_id>_curriculum`. Hits are joined back to `ContentNode` via
    `(document_id, node_id)` so callers see full citation metadata
    (title, page, node path). Returns dataclass `RetrievedChunk` instances.
    Vector-store failures are logged and yield empty results so the tutor
    never hard-errors.
  - `stub_answerer.py` — offline answerer used when `OPENAI_API_KEY` is
    unset. Returns `"Top sources for your question:\n\n[1] {title}\n
    {snippet}\n\n[2] ..."` verbatim (per planning decision: no fake
    reasoning).
  - `tutor_service.py::TutorService.answer_question(session, student, query,
    top_k=5)` — orchestrates one Q&A round in a single transaction:
    persists the student turn, retrieves chunks, branches to LLM or stub,
    persists the assistant turn with `retrieved_chunks` payload, refreshes
    `session.last_message_at`, and auto-titles the session from the first
    question. Validates ownership (student + tenant) and rejects empty
    queries. LLM exceptions fall back to the stub answerer with a logged
    warning.
- **2026-04-29 • api** • New REST namespace at
  `apps/service/api/`:
  - `serializers.py` — `TutoringSessionSerializer`,
    `TutoringSessionDetailSerializer` (nests messages),
    `ChatMessageSerializer`, `CreateMessageSerializer`.
  - `tutoring.py::TutoringSessionViewSet` — DRF `ViewSet` (not
    `ModelViewSet`) so every response goes through the project
    `APIResponse` envelope. Endpoints:
    - `POST   /api/v1/tutoring/sessions/`
    - `GET    /api/v1/tutoring/sessions/`
    - `GET    /api/v1/tutoring/sessions/<id>/`
    - `DELETE /api/v1/tutoring/sessions/<id>/` (archives via
      `is_active=False`)
    - `GET    /api/v1/tutoring/sessions/<id>/messages/`
    - `POST   /api/v1/tutoring/sessions/<id>/messages/` (the actual Q&A)
    All endpoints reject non-students (`is_student` guard) and 404 across
    tenant boundaries (no existence leakage).
  - `urls.py` — `DefaultRouter` with `service_api` URL namespace.
  - `config/urls.py` un-commented `path('api/v1/', include('apps.service.api.urls'))`.
- **2026-04-29 • web** • Student chat page:
  - `apps/web/views/student/chat.py::chat_view` — thin Django view that
    just renders the shell; the JS layer hydrates everything else through
    `APIClient`.
  - `apps/web/urls.py` — added fourth namespace `student_patterns` with
    `chat/` and `chat/<int:session_id>/` paths. Mounted at `/student/...`
    in `config/urls.py`.
  - `frontend/templates/student/chat.html` — two-column layout: session
    list on the left, conversation + composer on the right. Empty state
    when no session is selected. New-session modal (`<dialog>`) lets
    students pick an optional subject before opening a session.
  - `frontend/static/css/student.css` — chat-shell, session-row, bubble
    (student / assistant variants), citation chips, sources panel,
    composer, modal. Mobile collapses to single-column.
  - `frontend/static/js/student/chat.js` — uses the existing
    `APIClient`, renders `[N]` tokens as clickable citation chips that
    expand the matching source row. Cmd/Ctrl+Enter submits. Optimistic
    user bubble appears immediately, gets replaced with the persisted
    response. Shows an `offline` badge on assistant messages with
    `model='stub'`.
  - `frontend/templates/dashboards/student_dashboard.html` — wired the
    sidebar AI Tutor link to `student:chat`.
- **2026-04-29 • tests** • `apps/service/tests/test_tutoring.py` —
  16 passing tests, retriever and LLM both stubbed so tests run with no
  ChromaDB / sentence-transformers / OpenAI dependencies:
  - service: stub fallback, real-LLM happy path, LLM-failure fallback,
    empty-retrieval skips LLM, empty-query rejected, cross-student
    rejected, cross-tenant rejected, auto-title + `last_message_at` touch
  - api: list requires login, list scoped to current student, list
    forbidden for teachers, create returns 201, retrieve 404 across
    tenants, message POST persists both turns, message validation 400,
    message GET returns history, destroy archives.
- **2026-04-29 • verification** • `python manage.py check` clean;
  `python manage.py test apps.service` runs 21 tests (5 seeding + 16
  tutoring) green. Manual smoke (no LLM key, no embeddings):
  `GET /student/chat/` 200, `POST /api/v1/tutoring/sessions/` 201,
  `POST /api/v1/tutoring/sessions/<id>/messages/` 201 returning the
  honest offline-mode answer with `model='stub'`. Static assets
  (`/static/css/student.css`, `/static/js/student/chat.js`) served at 200.

### Tally update

- **Models in DB**: 11 → **13** (added `TutoringSession`, `ChatMessage`).
- **Lines of Python**: +~900 (service + api + tests + view).
- **Static frontend**: +1 CSS file (`student.css`, ~9 KB), +1 JS file
  (`student/chat.js`, ~10 KB), 1 new template (`student/chat.html`).
- **REST endpoints live**: 6 (under `service_api:` namespace).
- **Total tests**: 5 → **21** passing on `apps.service`.

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
