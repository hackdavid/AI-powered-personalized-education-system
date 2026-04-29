# EduAI Platform

AI-powered, multi-tenant personalized education platform built on Django 4.2.

## Documentation

All living documentation has been consolidated into the `docs/` folder:

- [`docs/project_aim.md`](docs/project_aim.md) — Mission, actors, end-to-end vision, success criteria.
- [`docs/memory.md`](docs/memory.md) — Architectural memory: tech stack, contracts, conventions, env vars.
- [`docs/progress.md`](docs/progress.md) — What's been shipped (append-only).
- [`docs/todo.md`](docs/todo.md) — Phased backlog of what's next.

## Quick start

```bash
python -m venv venv
venv\Scripts\activate                       # Windows
# source venv/bin/activate                  # macOS/Linux
pip install -r requirements/development.txt
copy .env.example .env                      # Windows
# cp .env.example .env                      # macOS/Linux
python manage.py migrate
python manage.py create_roles
python manage.py createsuperuser
python manage.py runserver
```

Visit http://127.0.0.1:8000/. See `docs/memory.md` section 11 for the full
command reference.

## Project layout

```
apps/
  core/        infrastructure (base models, middleware, decorators, APIResponse)
  accounts/    identity (User, Role, Permission, Tenant, AuthService, RBACService)
  service/     domain (models + business services + REST APIs)
  web/         presentation (HTML views, dashboards, forms)
clients/       external adapters (LLM, embeddings, vector store, storage)
config/        Django project settings + URLs
frontend/      static assets + templates
```

See `docs/memory.md` for the full map and the rules about which app does
what.
