# EduAI Platform — Project Aim & Goal

## Mission

Build an AI-powered, personalized, multi-tenant education platform that turns
curriculum content into adaptive learning experiences. Each school (tenant)
ingests its own books, the system grounds AI tutors in that material, teachers
generate assignments and track classes, and students learn through a gamified
goal-based loop instead of the traditional boring path.

## Actors

| Role | Primary jobs |
|---|---|
| **Student** | Use the AI tutor, answer assigned questions, set goals, level up XP, track own progress |
| **Teacher** | Create assignments (AI-generated questions), set due dates, view per-student heatmaps and analytics |
| **School Admin** | Manage classes, subjects, teachers, students. Upload curriculum books. Run ingestion. View school-level reports |
| **System Admin (us)** | Onboard schools, manage tenants, view system health, govern across all tenants |

## Core feature loops

1. **Ingestion loop** (school admin)
   `Upload PDF → extract text + images → discover TOC → outline chapters →
   structure content nodes via vision LLM → embed → ChromaDB collection per
   tenant.` Result: a queryable knowledge base.

2. **Tutoring loop** (student)
   `Student asks question → retrieve top-k content nodes from tenant's vector
   collection → LLM answers grounded in those nodes with citations → save chat
   history.` Result: a personalized tutor that never hallucinates curriculum.

3. **Assignment loop** (teacher → student → teacher)
   `Teacher picks topic + count + difficulty → AI generates questions → assign
   to class → students submit → AI auto-grades short/MCQ + teacher reviews
   essay → grades + feedback flow back.`

4. **Goal & progression loop** (student)
   `Student sets goal → system breaks it into tasks → completing tasks awards
   XP → XP raises level → badges unlock.` Anime-style "solo leveling" feel,
   not a tradition gradebook.

5. **Analytics loop** (teacher / school admin)
   `Submission scores + tutor activity + goal completion → per-student
   heatmaps, class-level dashboards, subject mastery views.`

## End-to-end vision (one paragraph)

A school admin signs up, uploads their textbooks, and the platform automatically
indexes them into a private knowledge base. Teachers in that school create
assignments by describing a topic — the platform generates questions grounded
in the school's books. Students log in to a personalized dashboard, see what's
due, set their own goals, and chat with an AI tutor that quotes their actual
syllabus. Teachers see live heatmaps of who's struggling on what. The
system-admin team monitors usage across all schools without ever seeing one
school's data leak into another's.

## Success criteria

- A new feature app can be added without modifying core infrastructure.
- A school's data never appears in another school's queries (tenant isolation
  enforced at DB and vector-store level).
- RAG answers cite their sources from the school's own materials.
- Role-based dashboards work end-to-end for all four roles.
- Health endpoint reports green on database, vector store, and LLM client.
- Frontend feature work uses `APIClient` / `Toast` / `FormHandler` / `Modal`
  with minimal boilerplate.

## Non-goals (deliberately out of scope)

- Live video classes, scheduling, or messaging.
- Mobile-native apps (browser-first; mobile via responsive web).
- Payment / billing integration (subscription tier is metadata only).
- Public/social features (no peer feeds, no chat between students).
- Replacing the school's official LMS — this augments, it doesn't replace.

## Architectural pillars

- **4-app Django layout** — `core` (infra), `accounts` (identity), `service`
  (domain + business logic + APIs), `web` (templates + dashboards).
- **External adapters** isolated under `clients/` (LLM, embeddings, vector
  store, storage). Swap providers without touching domain code.
- **Multi-tenancy first** — every domain row is scoped to a tenant; every
  vector collection is namespaced by tenant id.
- **Service-oriented** — fat models, thin views, smart services. Views never
  hold business logic; templates never call services directly.
- **Standardized contracts** — `APIResponse` for JSON, `@role_required` for
  authz, base models for timestamping/auditing.
