# Project memory

---

## Report 1: Full Academic Rewrite (CMP-L044 Part 1)

- **Goal:** Complete academic rewrite of the Part 1 report to meet 80-100% rubric band: research-grade prose, cross-checked IEEE references, industry-standard architecture diagrams, and five appendices (contributions, traceability, risk, glossary, evaluation plan).
- **Feature:** `doc/report1/` package fully rebuilt from scratch with academic tone, MSc-level reasoning, flowing narrative, and exactly **2000 words** (sections 1-9).
- **Architecture:** RAG education platform with C4/ISO 42010 architecture views; phased centralised-to-regional deployment; NIST AI RMF governance; ISO/IEC 5338 lifecycle alignment. Sixteen IEEE references [1]-[16] covering RAG, production ML, ITS, LLMs in education, MLOps, multi-tenant SaaS, and standards.
- **What I have done:**
  - Rewrote `report1-draft.md` from scratch: 9 sections, academic impersonal voice, minimal bold, proper transitions, hedging language, 2000 words verified by `_count_words.py`.
  - Rebuilt `references-ieee.md` with 16 cross-checked entries: verified DOIs, venues, page numbers; replaced arXiv-only preprints where possible (Asai Self-RAG confirmed at ICLR 2024); added Kasneci 2023, Kreuzberger 2023, ISO/IEC/IEEE 42010:2022, Bezemer 2010.
  - Rebuilt all 8 Mermaid diagrams in `diagrams/FIGURES.md` and `diagrams/export/*.mmd` with proper labels (no underscores), C4 framing, clean visual hierarchy. Rendered PNGs via `render-png.ps1`.
  - Created Appendix B: requirements traceability matrix (`APPENDIX-B-traceability.md`) mapping 10 FRs and 8 NFRs to architecture components and evaluation methods.
  - Created Appendix C: risk register (`APPENDIX-C-risk-register.md`) with 10 risks covering hallucination, wrong-region routing, ingestion failure, score drift, LLM outage, data breach, bias, over-reliance, gaming, vendor lock-in.
  - Created Appendix D: glossary (`APPENDIX-D-glossary.md`) with 16 technical terms.
  - Created Appendix E: evaluation plan (`APPENDIX-E-evaluation-plan.md`) with 9 metrics including targets and measurement methods.
  - Updated Appendix A (`APPENDIX-contributions.md`) to match new section structure: Daud (systems lead), Arbind (literature/appraisal), Luja (requirements/context), Vamshi (figures/diagrams), Aayush (RAI/governance/limitations).
  - Rebuilt `build_report_docx.py` to include all 5 appendices with proper Markdown table parsing; generated `CMP_L044_Report1_Group.docx` with body, 7 embedded figures, references, and all appendices.
- **Todo list:** Rename to Moodle submission format; group review for accuracy; add surnames for Luja, Vamshi, Aayush if required.

---

## EduAI Platform - Codebase Status (2026-04-20)

- **Location:** `code_base/eduai_platform/`
- **Stack:** Django 4.2, SQLite/PostgreSQL, OpenAI (configurable base_url), sentence-transformers, local ChromaDB, vanilla JS frontend
- **Phase 1 COMPLETE:** Core infrastructure, auth/RBAC (4 roles, 19 permissions), multi-tenancy, frontend utilities (APIClient, Toast, FormHandler, Modal), role-based dashboards, landing page
- **Phase 2 COMPLETE:** AI services layer
  - `services/ai/llm_service.py` - OpenAI-compatible LLM with configurable base_url, model_name, api_key. Supports RAG via generate_with_context()
  - `services/ai/embedding_service.py` - Free all-MiniLM-L6-v2 (384-dim), loaded at server startup via ServicesConfig.ready()
  - `services/ai/question_generator.py` - Generates MCQ/true-false/short-answer/essay questions via LLM
  - `services/vector_store/client.py` - Local ChromaDB PersistentClient, tenant-scoped collections, auto-embedding search
  - `services/apps.py` - AppConfig that pre-loads embedding model
- **School Admin Portal COMPLETE:** Full CRUD for classes, subjects, class-subject assignment, teacher invite (credentials shown on screen), student invite, book/document upload. All at `/school-admin/` with slide-in panel UX.
- **Phase 3 TODO:** Feature apps - ingestion pipeline, RAG tutoring, assessments, analytics, goals
- **Phase 4 TODO:** Production - Celery, Redis, S3, tests
- **Architecture:** Abstract base models, service-oriented design, tenant middleware, centralized APIResponse
- **Rules:** No new .md files created; update progress.md and memory.md instead

---
