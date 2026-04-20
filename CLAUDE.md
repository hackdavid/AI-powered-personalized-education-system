# CLAUDE.md - EduAI Platform

## Project Overview

EduAI Platform is a Django-based AI-powered personalized education system with RAG-based tutoring, multi-tenant architecture, and role-based access control. University project for Roehampton AI Engineering course.

## Tech Stack

- **Backend**: Django 4.2, Python 3.9+
- **Database**: SQLite (dev) / PostgreSQL (prod)
- **AI/ML**: OpenAI API, Anthropic Claude, LangChain, ChromaDB
- **Frontend**: Vanilla JS with utility modules (APIClient, Toast, FormHandler, Modal)
- **Task Queue**: Celery + Redis (planned for production)

## Project Structure

```
eduai_platform/
├── config/          # Django settings (base/development/production)
├── apps/
│   ├── core/        # Middleware, base models, decorators, APIResponse utility
│   ├── accounts/    # User, Role, Permission models + AuthService, RBACService
│   ├── tenants/     # Multi-tenant management (Tenant model)
│   ├── common/      # Shared models (Subject, Class, ClassSubject)
│   ├── ingestion/   # Document processing pipeline (NOT YET IMPLEMENTED)
│   ├── tutoring/    # RAG-based AI tutor (NOT YET IMPLEMENTED)
│   ├── assessments/ # Assignment management (NOT YET IMPLEMENTED)
│   ├── analytics/   # Student analytics (NOT YET IMPLEMENTED)
│   ├── goals/       # Gamified goals (NOT YET IMPLEMENTED)
│   └── monitoring/  # Health checks (NOT YET IMPLEMENTED)
├── frontend/
│   ├── static/js/core/  # api-client.js, toast.js, forms.js, modal.js
│   ├── static/css/      # core.css, dashboard.css
│   └── templates/       # base templates, dashboards, auth, components
├── services/
│   ├── ai/              # LLM, embedding, question generation (NOT YET IMPLEMENTED)
│   ├── vector_store/    # ChromaDB client (NOT YET IMPLEMENTED)
│   └── storage/         # Object storage (NOT YET IMPLEMENTED)
├── requirements/        # base.txt, development.txt, production.txt
├── fixtures/            # Test seed data
├── tests/               # unit/, integration/, e2e/ (NOT YET IMPLEMENTED)
├── docs/                # Additional documentation
└── manage.py
```

## Architecture Patterns

- **Base Models**: Use `TimestampedModel`, `TenantAwareModel`, `AuditModel`, `SoftDeleteModel` from `apps.core.models.base`
- **API Responses**: Always use `APIResponse.success()` / `APIResponse.error()` from `apps.core.utils.response`
- **View Protection**: Use `@role_required`, `@tenant_required`, `@log_action` decorators from `apps.core.decorators`
- **Frontend**: Use provided APIClient, Toast, FormHandler, Modal classes - no jQuery
- **Services**: Business logic goes in `services/` modules, not views. Fat models, thin views, smart services.
- **Multi-tenancy**: All data models extend `TenantAwareModel` for automatic tenant isolation

## Roles & Permissions

- **Student**: Limited access - own assignments, progress, tutoring
- **Teacher**: Class management, assignment creation, student progress
- **School Admin**: Tenant-wide user and class management
- **System Admin**: System-wide access across all tenants

## Current State

- **Phase 1 COMPLETE**: Core infrastructure, auth, RBAC, multi-tenancy, frontend utilities, dashboards
- **Phase 2 TODO**: AI services (LLM, embeddings, vector store)
- **Phase 3 TODO**: Feature apps (ingestion, tutoring, assessments, analytics, goals)
- **Phase 4 TODO**: Production readiness (Celery, Redis, S3, testing)

## Running the Project

```bash
# From eduai_platform/
pip install -r requirements/development.txt
python manage.py migrate
python manage.py create_roles
python manage.py createsuperuser
python manage.py runserver
```

Key URLs: `/` (landing), `/auth/login/`, `/health/`, role-specific dashboards

## Coding Conventions

- Python: PEP 8, type hints, Black formatter
- Django: One model per file in `models/` directory
- JavaScript: ES6+, camelCase vars, PascalCase classes
- No docstrings on obvious code; short comments only for non-obvious WHY

## Rules

- **DO NOT create new .md files** in this project. Instead, update `memory.md` and `progress.md` at the project root (`ai_engineering/`) whenever work is completed.
- When finishing any task, append a summary to `progress.md` and update `memory.md` if there are durable learnings.
