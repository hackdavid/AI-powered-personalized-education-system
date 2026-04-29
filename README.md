# EduAI Platform

> A multi-tenant, RAG-grounded AI tutor for schools. Each school's curriculum becomes a private knowledge base; students chat with an AI that quotes their actual textbooks instead of making things up.

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.1-darkgreen.svg)](https://www.djangoproject.com/)
[![Postgres](https://img.shields.io/badge/Postgres-17.6-336791.svg?logo=postgresql&logoColor=white)](https://supabase.com/)
[![pgvector](https://img.shields.io/badge/pgvector-0.8-1976d2.svg)](https://github.com/pgvector/pgvector)
[![Tests](https://img.shields.io/badge/tests-63%2F63%20passing-brightgreen.svg)]()
[![License](https://img.shields.io/badge/license-academic-lightgrey.svg)]()

---

## What this is

A web platform that takes a school's curriculum (textbooks, notes, exercises) and turns it into:

- 🤖 **A grounded AI tutor** for students that retrieves passages from the school's own materials and answers with citations — no hallucinated curriculum.
- 📚 **A school admin portal** to manage classes, subjects, teachers, students, and curriculum books.
- 🧪 **A teacher assignment workflow** *(planned)*: pick a topic, AI generates questions, students submit, auto-grading flows back as analytics.
- 🎯 **A student goal / XP loop** *(planned)*: anime-style "solo leveling" progression instead of a traditional gradebook.

Built as a course project for **CMP-L044 (AI Engineering)** at Roehampton, but designed as a real product — multi-tenant from day 1, deployable to a single Render service, and able to run end-to-end on free tiers.

## Why it exists

Three things wrong with both "ChatGPT for homework" and traditional LMS tooling:

1. **Hallucination problem.** Generic LLMs cheerfully invent quotes from textbooks they've never seen. Students fail tests by citing the wrong formula.
2. **Per-school content problem.** Real schools use specific textbooks. A useful tutor needs to be grounded in *their* `Math Grade 9 Chapter 2`, not a generic Wikipedia summary.
3. **Tooling fragmentation.** Teachers waste hours assembling assignments, grading, and tracking who's struggling. The data is there; the loop isn't closed.

EduAI closes the loop: every school gets an isolated knowledge base, every answer cites its source, every student sees their own progression, every teacher sees per-student heatmaps. The platform stays small and replaceable — vector store, LLM, and embedder are all swappable adapters under `clients/`.

## Architecture

```
        Browser (HTTPS)
              │
              ▼
   ┌─────────────────────────────┐         ┌──────────────────────────┐
   │  Render (Docker / Gunicorn) │         │ HuggingFace Space        │
   │  • Django 5 + DRF           │ ──HTTP──▶ • all-MiniLM-L6-v2 (384d) │
   │  • Auth, RBAC, multi-tenant │         │ • FastAPI /embed endpoint │
   │  • Tutor RAG + chat UI      │         └──────────────────────────┘
   │  • School admin portal      │
   └────────────┬────────────────┘
                │ SQL + pgvector cosine search
                ▼
   ┌─────────────────────────────┐
   │  Supabase Postgres          │
   │  • All ORM data             │
   │  • ContentEmbedding (HNSW)  │
   │  • AppSetting (runtime cfg) │
   └─────────────────────────────┘
```

Three deployment artefacts, one shared platform:

| Component | Where | Why split |
|---|---|---|
| **Django app** | Render (Docker) | Stateless; redeploy in minutes; horizontal scale |
| **Postgres + pgvector** | Supabase | Managed; free tier covers a class-sized deployment; backups built in |
| **Embedding service** | HuggingFace Space | Avoids `torch` install hell on team laptops; CPU is plenty for `all-MiniLM-L6-v2` |

## Key features

- **Multi-tenant by default.** Every domain row carries a `tenant` FK; pgvector queries filter by `tenant_id`; one school's curriculum can never leak into another's tutor answers.
- **RAG tutor with citations.** `CurriculumRetriever` does cosine-distance HNSW search over the school's `ContentEmbedding`s, surfaces the top-5 chunks, and renders them as numbered `[1]`, `[2]` citations a student can click to verify.
- **Pluggable embedder.** Default: remote HuggingFace Space (no local `torch`). Fallback: in-process `sentence-transformers`. One `EMBEDDING_PROVIDER` env switch.
- **Pluggable LLM.** OpenAI-compatible client; works with OpenAI, Azure OpenAI, Ollama, anything that speaks the OpenAI chat-completions protocol.
- **Offline mode for free demos.** When no `OPENAI_API_KEY` is configured, the tutor falls back to a stub answerer that returns the retrieved sources verbatim — full retrieval works, zero LLM spend.
- **Runtime-editable settings.** `AppSetting` table + Django admin = rotate secrets without redeploys. One trusted admin sets keys; team-mates never see them.
- **REST API.** DRF ViewSet under `/api/v1/tutoring/` for chat sessions and messages; same `APIResponse` envelope across the codebase.
- **Synthetic data seed.** 2 demo tenants + 182 users + 12 textbooks + 148 embeddings ready to play with via `seed_synthetic_data --reset --with-embeddings`.

## Tech stack

| Layer | Choice |
|---|---|
| Runtime | Python 3.12, Django 5.1, Gunicorn |
| API | Django REST Framework + custom `APIResponse` envelope |
| Database | Postgres 17 on Supabase (pooler URL, port 6543) |
| Vector store | pgvector 0.8 with HNSW cosine index, 384-dim vectors |
| Embedder | `sentence-transformers/all-MiniLM-L6-v2` on a HuggingFace Docker Space |
| LLM | OpenAI-compatible API (offline stub fallback) |
| Frontend | Vanilla JS (`APIClient`, `Toast`, `FormHandler`, `Modal`), Tailwind via CDN |
| Static files | WhiteNoise (`CompressedManifestStaticFilesStorage`) |
| Auth | Django sessions; custom `User` model on email; 4 roles (Student / Teacher / SchoolAdmin / SystemAdmin) |
| Multi-tenancy | `TenantMiddleware` resolves tenant from subdomain or `request.user.tenant`; `TenantAwareModel` base class |
| Deploy | Render (Docker runtime, autoDeploy on `main`) |
| Tests | Django's built-in test runner; 63 tests, mock the LLM + embedder layers |

## Quick start (local development)

There are two paths. **Path A** is the one you want — it points your local app at the team's shared Supabase + HuggingFace Space, so you skip every install / migration / seed step.

### Path A — connect to the shared dev DB (~3 minutes)

```bash
git clone <this-repo>
cd eduai_platform

# 1. Install Python deps. NO torch — it's not in requirements.txt.
python -m venv venv
venv\Scripts\activate              # Windows
# source venv/bin/activate         # macOS / Linux
pip install -r requirements.txt

# 2. Copy the minimal env template and fill in three values.
cp .env.local.example .env         # macOS / Linux
# copy .env.local.example .env     # Windows
```

Open `.env` and set:

| Var | Where to get it |
|---|---|
| `DJANGO_SECRET_KEY` | Run `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DATABASE_URL` | Ask the project owner for the **Supabase transaction-pooler URL** (port `6543`) |
| (rest pre-filled) | `DJANGO_DEBUG=True`, etc. |

Then:

```bash
python manage.py runserver
# → http://127.0.0.1:8000/
```

That's it. No `migrate`, no `create_roles`, no `seed_synthetic_data` — the shared Supabase already has everything. Log in with one of the [demo accounts](#demo-accounts) below.

### Path B — fully local (SQLite, no shared DB)

For when you don't have the shared `DATABASE_URL` (or want a sandbox to break):

```bash
git clone <this-repo>
cd eduai_platform
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# In .env: leave DATABASE_URL blank, set DJANGO_DEBUG=True, set DJANGO_SECRET_KEY

python manage.py migrate
python manage.py create_roles
python manage.py bootstrap_app_settings --include-secrets
python manage.py seed_synthetic_data --reset --with-embeddings
python manage.py createsuperuser
python manage.py runserver
```

This builds a private SQLite DB at `db.sqlite3` and seeds 148 embeddings against the shared HuggingFace embedder Space (~30 s).

## Demo accounts

The seed creates **182 demo users** across two synthetic tenants. Default password for everyone: `Test@1234`.

| Role | Tenant | Email |
|---|---|---|
| School Admin | Springfield | `admin@springfield.test` |
| School Admin | Riverside | `admin@riverside.test` |
| Teacher | Springfield | (any of 10 — see `User.objects.filter(role__name='teacher', tenant__slug='springfield')`) |
| Student | Springfield | e.g. `william.king.79@springfield.test` |
| Django superuser | — | created via `createsuperuser` |

After login, students land at `/dashboard/` → "AI Tutor" sidebar link → chat about anything in the curriculum. Try *"What is the discriminant of a quadratic?"* — you'll see grounded sources from `math-grade-9.yaml`.

## Configuration

The platform reads settings from three layers, in this order:

```
1. AppSetting DB rows (runtime, hot-editable)   ← admin-managed at /admin/core/appsetting/
2. .env file (boot-time)                         ← per-developer secrets
3. Defaults in config/settings.py                ← code
```

Everything sensitive (LLM keys, embedder secret, model names, URLs) lives in **layer 1** — the admin pastes them into Django admin once and the rest of the team never sees them.

- See [`docs/admin_setup.md`](docs/admin_setup.md) for the full list of `AppSetting` keys and how to configure them.
- See [`.env.example`](.env.example) for every env-var default with explanations.
- See [`docs/memory.md`](docs/memory.md#8-config--environment-variables) §8 for the env-var resolution table.

### Offline mode (default)

Out of the box, `OPENAI_API_KEY` is **inactive** — the tutor uses a stub answerer that returns the retrieved sources verbatim. Real RAG retrieval still happens; you just don't pay for LLM tokens. Flip `OPENAI_API_KEY` active in admin + restart the server when you want natural-language answers.

## Deployment

Production target is **Render** (Docker runtime, autoDeploy from `main`). Postgres stays on Supabase, embedder stays on HuggingFace Space — Render hosts only the Django app.

```
git push origin main
   │
   ▼  Render watches the branch
   ├─ docker build (Dockerfile)
   ├─ python manage.py migrate --noinput   ← preDeployCommand
   ├─ start Gunicorn on $PORT
   └─ wait for /health/ → 200, then swap traffic
```

`render.yaml` pre-fills 9 env vars; you only paste two secrets (`DATABASE_URL`, `EMBEDDER_API_KEY`) into the Render dashboard. Full walkthrough in **[`docs/deployment.md`](docs/deployment.md)**.

## Project structure

```
eduai_platform/
├── manage.py
├── requirements.txt              # single requirements file, all environments
├── .env.example                  # full reference of every env var
├── .env.local.example            # 3-line minimum for new contributors
├── Dockerfile                    # production runtime image
├── render.yaml                   # Render service blueprint
│
├── config/
│   ├── settings.py               # single file; DEBUG flag toggles dev/prod
│   └── urls.py                   # / , /auth/* , /school-admin/* , /student/* , /api/v1/* , /admin/ , /health/
│
├── apps/
│   ├── core/                     # base models, middleware, decorators, APIResponse, AppSetting, /health
│   ├── accounts/                 # User, Role, Permission, Tenant; auth + RBAC services
│   ├── service/                  # domain models + services + DRF API
│   │   ├── models/               # Subject, Class, Document, ContentNode, ContentEmbedding, TutoringSession, ChatMessage
│   │   ├── services/             # tutoring, ingestion, seeding, assessments
│   │   └── api/                  # DRF ViewSets (TutoringSession + nested messages)
│   └── web/                      # presentation: views, forms, templates URLs
│       └── views/{auth, dashboards, school_admin, student, public}
│
├── clients/                      # external adapters — NOT a Django app
│   ├── llm/                      # OpenAI-compatible client
│   ├── embeddings/               # remote HF Space + local sentence-transformers fallback
│   └── vector_store/             # pgvector client (same facade as old ChromaDB code)
│
├── frontend/
│   ├── static/                   # css, js (core utilities + per-page bundles)
│   └── templates/                # base, components, dashboards, auth, school_admin, student
│
├── fixtures/synthetic_books/     # 6 hand-authored YAML textbooks
├── docs/                         # project_aim, memory, progress, todo, admin_setup, deployment
└── apps/service/tests/           # 63 tests (seeding, tutoring, embedder, pgvector, AppSetting)
```

The 4-app rule: **plumbing → core, who → accounts, what → service, screens → web, external → clients/**.

## Testing

```bash
python manage.py test apps          # 63 tests, ~35 s on SQLite
```

The suite mocks the LLM and remote embedder, so it doesn't need network access or the HF Space to be warm:

| File | Tests | Covers |
|---|---|---|
| `apps/service/tests/test_seeding.py` | 5 | synthetic data idempotency, tenant isolation |
| `apps/service/tests/test_tutoring.py` | 16 | TutorService stub/LLM branches, DRF ViewSet, RBAC, cross-tenant 404s |
| `apps/service/tests/test_embeddings_remote.py` | 13 | RemoteEmbeddingService HTTP behaviour (auth, retries, errors) |
| `apps/service/tests/test_pgvector_client.py` | 17 | VectorStoreClient facade, add/search/delete, tenant scoping |
| `apps/core/tests/test_app_setting.py` | 12 | runtime-settings model, override → settings, bootstrap idempotency |

## Documentation

All living docs are in `docs/` and stay up to date with the codebase:

| Doc | What it's for |
|---|---|
| [`docs/project_aim.md`](docs/project_aim.md) | Mission, actors, end-to-end vision, success criteria |
| [`docs/memory.md`](docs/memory.md) | Architectural memory: tech stack, contracts, conventions, env vars, runtime AppSetting layer |
| [`docs/progress.md`](docs/progress.md) | Append-only ledger of what's been shipped per phase |
| [`docs/todo.md`](docs/todo.md) | Phased backlog of what's next |
| [`docs/admin_setup.md`](docs/admin_setup.md) | Step-by-step `AppSetting` configuration for the trusted admin |
| [`docs/deployment.md`](docs/deployment.md) | Full Render deploy walkthrough (Blueprint, secrets, gotchas, rollback) |

## Roadmap

> Numbering note: the original [`docs/todo.md`](docs/todo.md) plan numbers user-facing
> features as Phase 0 → 7. The infrastructure work that landed alongside
> Phase 2 is tracked separately as Phase 2.5–2.7 and 3A–3D in
> [`docs/progress.md`](docs/progress.md) — different track, same project.

### Infrastructure / platform — done ✅

- Phase 0 — 4-app refactor + 4 living docs
- Phase 1 — Synthetic curriculum (markdown books, multi-tenant)
- Phase 2 — RAG tutor (chat UI, citations, DRF, 16 tests)
- Phase 2.5 — Embeddings externalised to HuggingFace Space
- Phase 2.6 — Admin-editable runtime settings (`AppSetting`)
- Phase 2.7 — Single `settings.py` + single `requirements.txt`
- Phase 3A — Shared Postgres on Supabase
- Phase 3B — pgvector replaces ChromaDB
- Phase 3C — ChromaDB removed, onboarding examples added
- Phase 3D — Render deployment plumbing (Dockerfile + render.yaml)

### Features — up next 🔜

- **Assessments** (Phase 3 in `todo.md`) — teacher-side AI question generation, student submission, auto-grading
- **Analytics** (Phase 4) — per-class heatmaps, per-student mastery
- **Goals & XP** (Phase 5) — gamified progression loop
- **Real PDF ingestion** (Phase 6) — pipeline already built; needs DRF endpoints + UI
- **Production hardening** (Phase 7) — Celery, Redis, S3, e2e tests, CI

## Contributing

1. Pick an item from `docs/todo.md`.
2. Read the matching section in `docs/memory.md` (especially §4 contracts and §7 naming).
3. Branch off `main`, push to GitHub, open a PR.
4. Keep `docs/progress.md` and `docs/memory.md` in sync with what you ship — these docs are the contract for the team and the LLM helpers picking up this codebase.

Tests must stay green: `python manage.py test apps`.

## Acknowledgements

- [`pgvector`](https://github.com/pgvector/pgvector) — Postgres extension that makes 384-dim cosine search a single SQL query
- [`sentence-transformers`](https://www.sbert.net/) — `all-MiniLM-L6-v2` for the embedding model
- [Supabase](https://supabase.com/) — managed Postgres + pgvector + dashboard
- [HuggingFace Spaces](https://huggingface.co/spaces) — free CPU host for the embedding microservice
- [Render](https://render.com/) — autoDeploy + Docker runtime for the Django app
- Roehampton **CMP-L044 (AI Engineering)** course staff and group members

## License

Academic project — see `docs/todo.md` Phase 7 for the licensing decision. Until then: not yet open source; please don't redistribute.
