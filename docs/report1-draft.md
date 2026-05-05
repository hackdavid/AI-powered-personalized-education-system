# AI-Powered Personalised Education Platform: Systems Engineering Proposal

**Module:** CMP-L044 AI Systems Engineering
**Group:** [Group number]

## Declaration of Use of Generative AI

Generative AI tools (Cursor, ChatGPT) were used for language refinement and diagram drafting (Mermaid). All technical claims, architectural decisions, literature analysis, and citations were independently verified by the authors. The Appendix details each member's contribution by section.

---

## 1. Introduction and Problem Statement

Meta-analytic evidence demonstrates that intelligent tutoring systems produce learning gains comparable to human tutoring when well-implemented [1], yet mainstream schooling continues to rely on uniform pacing, periodic summative assessment, and delayed feedback. General-purpose large language models (LLMs) such as GPT-3 [2] offer conversational fluency but lack institutional curriculum grounding, auditable progression tracking, and the governance structures that schools require.

This report addresses a specific engineering question: how to architect a retrieval-augmented generation (RAG) system that delivers curriculum-aligned tutoring, adaptive practice, and formative assessment while satisfying data-residency, teacher-oversight, and reproducibility constraints. Success is defined through measurable criteria: retrieval precision on curated question sets, grading calibration error benchmarked against teacher labels, interactive latency at the 95th percentile, and an auditable record linking every response to its source material.

The risks extend beyond the technical. Model hallucination erodes institutional trust; inconsistent scoring undermines teacher confidence; and incorrect data routing across jurisdictions creates regulatory exposure. Each consequence motivates specific architectural controls discussed in subsequent sections.

From a systems engineering perspective, the challenge is to compose data stores, orchestration services, evaluation harnesses, and human workflows into a reliable whole rather than to optimise a single model. Sculley et al. [3] characterise ML systems as prone to hidden technical debt when infrastructure is neglected, and Amershi et al. [4] demonstrate that software engineering practices must be adapted for ML-intensive products. The platform is accordingly treated as an end-to-end engineered system.

## 2. System Context and Boundary

Four stakeholder groups shape the design: students seeking personalised feedback; teachers requiring analytics and rubric-based grading support; school administrators responsible for policy compliance and outcome metrics; and platform operators managing reliability and incident response. The operating environment comprises web clients connecting to managed cloud infrastructure, with optional integration points for single sign-on (SSO) and learning management system (LMS) connectors.

Fig. 1 presents a context-level view following ISO/IEC/IEEE 42010 conventions [15]. External actors interact through web interfaces; SSO and LMS appear as optional dependencies with dashed connectors, indicating the system remains operational in their absence. Back-office finance systems and social networks are excluded.

Schools onboard voluntarily and upload curriculum as document files; no mandatory integration with legacy student information systems is required initially. Trust boundaries ensure that curriculum content and learner data never cross a tenant without an auditable policy check, establishing the foundation for regional isolation discussed in Section 5.

## 3. Functional and Non-Functional Requirements

The functional scope is organised around five capability clusters. First, curriculum ingestion: the system must accept PDF and DOCX uploads, extract text, segment content into retrievable chunks, and maintain versioned document identifiers. Second, retrieval and generation: embedding-based search over a per-tenant vector index must return source-cited answers grounded in uploaded material [5]. Third, adaptive practice: question difficulty must adjust to the learner's demonstrated proficiency across topics. Fourth, assessment: rubric-aware scoring must combine automated LLM evaluation with mandatory teacher override for summative decisions. Fifth, governance: role-based access control (RBAC), audit logging of prompts and model versions, and data export for school-owned records.

Non-functional requirements reflect the operational realities of classroom deployment. Latency targets for interactive sessions must be specified at the 95th percentile to avoid disrupting lesson flow. Horizontal scalability must accommodate concurrent classes across time zones. A 99.9% availability objective during class hours sets the resilience baseline. Encryption in transit and at rest, regional data residency for international deployments, and full auditability of generated scores are not optional enhancements but architectural invariants. Reproducibility of experiments and graded outputs follows the disciplined practices advocated for production machine learning [8], [9].

Quality attributes are prioritised for the initial evidence-building phase: correctness of grounding and teacher trust take precedence over model novelty; availability of the tutoring path over exhaustive analytics; and security of tenant isolation over feature breadth.

## 4. Literature Review and Critical Appraisal

The design draws on four intersecting bodies of literature: retrieval-augmented generation, production machine learning systems, intelligent tutoring, and responsible AI governance.

Lewis et al. [5] introduced RAG by coupling a parametric model with a dense retrieval index, demonstrating improved factual grounding on knowledge-intensive tasks. Subsequent surveys [6] catalogue RAG variants and failure modes, while Asai et al. [7] propose Self-RAG, where the model learns to decide when retrieval is necessary and critiques its own outputs through reflection tokens. Self-RAG is relevant to educational assessment because grading must be defensible: a system that withholds a response when evidence is insufficient is safer than one that always generates. However, RAG alone does not address calibration or the challenge of aligning feedback with institutional rubrics.

Production ML literature provides the operational foundation. Sculley et al. [3] identify data dependencies and monitoring as sources of technical debt. Polyzotis et al. [8] extend this to data management challenges including lineage and validation. Kreuzberger et al. [9] survey MLOps practices for continuous integration, deployment, and monitoring. These frameworks target supervised learning pipelines; LLM-based RAG systems introduce additional concerns around prompt management, retrieval drift, and non-deterministic output that demand further adaptation.

Evidence from learning science grounds the educational claim. Kulik and Fletcher [1] report meaningful effect sizes for intelligent tutoring, though outcomes depend on domain content and pedagogical integration rather than model scale. Kasneci et al. [10] examine LLMs in education, emphasising that integration requires teacher and learner competencies, oversight mechanisms, and strategies to address the inherent brittleness of generative models.

The NIST AI Risk Management Framework [11] organises governance through Map, Measure, and Manage functions. Mehrabi et al. [12] survey fairness concerns acute when scoring affects learner outcomes across subgroups. The General Data Protection Regulation [13] imposes data minimisation and subject access obligations relevant to systems serving minors. ISO/IEC 5338 [14] defines lifecycle processes providing internationally recognised structure for AI system design and validation.

### 4.1 Two Engineering Approaches Compared

Two deployment architectures merit comparison. Approach A, a centralised single-region deployment, offers the fastest path to a functional prototype: one application stack, one database cluster, simpler networking, and straightforward backup and debugging. Its limitation is that it cannot satisfy data-residency requirements for schools in multiple jurisdictions and concentrates operational risk in a single failure domain.

Approach B distributes the data plane across regions while maintaining a lightweight global metadata control plane that maps each school to its designated region, consistent with established multi-tenant SaaS isolation patterns [16]. This architecture aligns with GDPR-style data localisation expectations [13] and supports portable container images with region-specific configuration. The cost is greater operational complexity: routing misconfiguration can produce compliance failures, and cross-region consistency and disaster recovery require deliberate engineering.

The proposed strategy adopts a phased approach. Approach A is implemented first to validate pedagogical effectiveness and retrieval quality. Architectural affordances for regional migration, including tenant-scoped identity routing, infrastructure-as-code templates, and configuration-driven service binding, are engineered from the outset so that the transition to Approach B requires provisioning and replication rather than structural redesign. This phased rationale aligns with the iterative lifecycle model described in ISO/IEC 5338 [14].

A third design axis concerns retrieval quality. Dense-only retrieval is operationally simpler in early phases; hybrid sparse-dense methods improve lexical matching for named entities common in syllabi; and self-critique loops [7] strengthen verification at the cost of increased latency. The appropriate configuration depends on the stakes of the task: formative practice may tolerate faster, simpler retrieval, while summative assessment benefits from stricter verification.

The gap this proposal addresses is the absence of integrated engineering narratives that co-design retrieval, tutoring, regional compliance, teacher oversight, and operational monitoring as a single coherent system rather than treating each concern in isolation.

## 5. Proposed Architecture and Data Strategy

The architecture is described through multiple complementary views following the conventions of ISO/IEC/IEEE 42010 [15].

The logical view (Fig. 2) decomposes the system into four layers: presentation (web clients); application services (ingestion, retrieval, tutor, grading, analytics); a data plane (object storage, versioned vector index, relational store); and a model layer (embedding and LLM inference behind policy wrappers). Each service boundary is defined by an interface contract, limiting the scope of change when a component is updated independently.

The data pipeline view (Fig. 3) traces documents from upload through extraction, chunking, embedding, and index population. Builds are idempotent and versioned. An offline evaluation loop compares retrieval against golden question sets, providing a regression gate before index promotion.

The interaction view (Fig. 4) presents the RAG sequence: a query is embedded and matched against top-k chunks; the LLM generates a cited response; the grading service optionally applies rubric scoring; and the event store logs the prompt hash, model version, chunk identifiers, and score.

Evaluation uses frozen rubrics paired with teacher labels. Experimentation follows disciplined release practice [4], [9]: offline comparisons precede canary deployments with expanded logging and automatic rollback on quality regression.

## 6. Deployment, Operations, Monitoring, and Incidents

The deployment view (Fig. 5) illustrates the multi-region topology. Container images are promoted identically across regions; environment-specific configuration selects storage, database, and model endpoints. Infrastructure-as-code ensures new regional deployments are parameterised replications rather than bespoke constructions.

The observability architecture (Fig. 6) captures latency percentiles, retrieval hit rate, grading variance drift, and error rates. Distributed tracing links each request to retrieved chunks and model version. Alerts feed runbooks classified by severity: wrong-region routing triggers rollback and access audit; ingestion failure quarantines content; score drift suspends automated grading; and provider outage activates degraded read-only mode. Post-incident reviews feed the risk register, closing the NIST AI RMF Measure and Manage loop [11].

Reproducibility is enforced through prompt hashes, temperature settings, and seeds stored alongside model cards. Cost is managed via retrieval caching, batched inference, and right-sized models for embedding versus generation.

## 7. Responsible AI and Governance

Responsible AI considerations are integrated throughout the design rather than appended as a separate concern. The NIST AI Risk Management Framework [11] structures the governance approach. Under Map, the system identifies risk contexts specific to education: automated scoring of minors, potential for pedagogical harm through incorrect feedback, and data protection obligations. Under Measure, subgroup error analysis monitors fairness where sample sizes support meaningful comparison [12]. Under Manage, teacher override capabilities, audit trails linking every score to its evidence, and data subject access request (DSAR) processes under GDPR [13] provide actionable governance mechanisms.

Transparency is achieved by surfacing source citations and rubric criteria to both students and teachers (Fig. 7). Student wellbeing considerations include discouraging overuse through interface design and providing teacher contact pathways when keyword heuristics detect potential distress, without the system claiming clinical capability. Content safety filters apply to both user uploads and model outputs with escalation pathways for moderation.

## 8. System Limitations and Design Boundaries

The inherently stochastic nature of language model outputs means that grounding and grading can fail in edge cases despite strong aggregate performance metrics. Retrieval coverage depends directly on the quality of uploaded curriculum; topics absent from ingested material cannot be addressed authoritatively. Automated scoring carries calibration and fairness risks at small sample sizes [12], which is precisely why teacher override and audit trails are architectural requirements rather than optional features. Third-party LLM and embedding providers introduce availability, latency, and contractual dependencies outside the platform's direct control. Transparency mechanisms build legitimacy but cannot guarantee trust; the design therefore preserves teacher professional agency as a foundational principle.

## 9. Conclusion

This report has framed curriculum-grounded personalised learning as an AI systems engineering challenge, drawing on retrieval-augmented generation for factual grounding [5], [7], production ML discipline for operational longevity [3], [9], and governance frameworks for institutional trust [11], [14]. The phased deployment strategy balances the pragmatism of centralised validation against the compliance demands of regional distribution. The accompanying views present the system across context, logical architecture, data pipeline, deployment, observability, and governance at the level of rigour expected of a production-aware engineering proposal.

---

## References

[1]-[16] as listed in references-ieee.md.

---

## Appendix

See APPENDIX-contributions.md and supplementary appendices B-E.
