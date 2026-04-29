"""
Seed synthetic curriculum data for one or more tenants.

Pipeline (per tenant):

    1. Create / reuse the tenant.
    2. Optionally reset existing synthetic rows scoped to the tenant.
    3. Seed users (school admin + teachers + students) using faker.
    4. Seed Subjects, Classes, and ClassSubject mappings.
    5. Seed Documents + ContentNode trees from
       `fixtures/synthetic_books/*.yaml`.
    6. (Optional, --with-embeddings) embed every node and upsert into the
       tenant's ChromaDB collection.

The command is idempotent. Re-running it produces the same row counts.

Examples
--------
    # Default: seed both demo tenants with all books
    python manage.py seed_synthetic_data

    # Only seed one tenant, wipe its synthetic books first
    python manage.py seed_synthetic_data --tenant springfield --reset

    # Skip user generation (just refresh books)
    python manage.py seed_synthetic_data --books-only

    # Generate embeddings into ChromaDB as well
    python manage.py seed_synthetic_data --with-embeddings

Roles must already exist (`python manage.py create_roles`).
The default user password comes from `SEED_DEFAULT_PASSWORD` env var
(falls back to `Test@1234`).
"""

import logging
import sys
from typing import List

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Role, Tenant
from apps.service.services.seeding import (
    seed_books,
    seed_classes,
    seed_tenants,
    seed_users,
)
from apps.service.services.seeding.books import discover_book_files
from apps.service.services.seeding.classes import (
    DEFAULT_GRADE_LEVELS,
    seed_class_subjects,
    seed_subjects,
)
from apps.service.services.seeding.tenants import reset_tenant_synthetic_data


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Seed synthetic curriculum data (tenants, users, classes, books).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--tenant',
            action='append',
            default=None,
            metavar='SLUG',
            help='Tenant slug to seed. Repeat for multiple. Default: springfield, riverside.',
        )
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete existing synthetic Documents (and their ContentNodes) before seeding.',
        )
        parser.add_argument(
            '--books-only',
            action='store_true',
            help='Skip users / classes; only refresh books from YAML.',
        )
        parser.add_argument(
            '--users-only',
            action='store_true',
            help='Skip books; only seed tenants, users, classes.',
        )
        parser.add_argument(
            '--with-embeddings',
            action='store_true',
            help='After seeding, embed every synthetic ContentNode into ChromaDB. Slow on first run.',
        )
        parser.add_argument(
            '--seed',
            type=int,
            default=42,
            help='RNG seed for faker / random (deterministic users). Default: 42.',
        )

    # ------------------------------------------------------------------
    # Entrypoint
    # ------------------------------------------------------------------

    def handle(self, *args, **opts):
        if opts['books_only'] and opts['users_only']:
            raise CommandError("--books-only and --users-only are mutually exclusive.")

        self._verify_roles_exist()

        slugs = opts['tenant']
        tenants = seed_tenants(slugs)
        self._info(
            f"Tenants: {[t.slug for t in tenants]}",
            heading='Step 1/5'
        )

        totals = {
            'tenants': len(tenants),
            'users_created': {'school_admins': 0, 'teachers': 0, 'students': 0},
            'subjects': 0,
            'classes': 0,
            'class_subjects': 0,
            'documents_created': 0,
            'documents_updated': 0,
            'chapters': 0,
            'sections': 0,
            'topics': 0,
            'leaves': 0,
            'cross_refs': 0,
            'embeddings_added': 0,
        }

        for tenant in tenants:
            self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== Seeding tenant: {tenant.slug} ==="))

            if opts['reset']:
                stats = reset_tenant_synthetic_data(tenant)
                self._info(f"Reset: deleted {stats['documents_deleted']} synthetic documents.")

            teachers, students = self._seed_users_step(tenant, opts, totals)
            subjects_by_code, classes = self._seed_classes_step(tenant, teachers, opts, totals)
            self._seed_books_step(tenant, opts, totals)

            if opts['with_embeddings']:
                added = self._embed_tenant_nodes(tenant)
                totals['embeddings_added'] += added
                self._info(f"Embeddings: upserted {added} nodes into '{tenant.id}_curriculum'.")

        self._print_summary(totals, with_embeddings=opts['with_embeddings'])

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    def _seed_users_step(self, tenant: Tenant, opts: dict, totals: dict):
        if opts['books_only']:
            self._info("Users: skipped (--books-only).", heading='Step 2/5')
            existing_teachers = list(tenant.users.filter(role__name=Role.TEACHER))
            existing_students = list(tenant.users.filter(role__name=Role.STUDENT))
            return existing_teachers, existing_students

        users = seed_users(tenant, seed=opts['seed'])
        for k, v in users['created'].items():
            totals['users_created'][k] += v
        self._info(
            f"Users: school_admins=+{users['created']['school_admins']} "
            f"teachers=+{users['created']['teachers']} "
            f"students=+{users['created']['students']}",
            heading='Step 2/5',
        )
        return users['teachers'], users['students']

    def _seed_classes_step(
        self,
        tenant: Tenant,
        teachers,
        opts: dict,
        totals: dict,
    ):
        if opts['books_only']:
            self._info("Subjects/Classes: skipped (--books-only).", heading='Step 3/5')
            from apps.service.models import Class, ClassSubject, Subject
            subjects_by_code = {s.code: s for s in Subject.objects.filter(tenant=tenant)}
            classes = list(Class.objects.filter(tenant=tenant))
            return subjects_by_code, classes

        subjects_by_code = seed_subjects(tenant)
        classes = seed_classes(tenant, teachers=teachers)
        class_subjects = seed_class_subjects(classes, subjects_by_code, teachers)

        totals['subjects'] += len(subjects_by_code)
        totals['classes'] += len(classes)
        totals['class_subjects'] += len(class_subjects)

        self._info(
            f"Subjects/Classes: subjects={len(subjects_by_code)} "
            f"classes={len(classes)} class_subjects={len(class_subjects)}",
            heading='Step 3/5',
        )
        return subjects_by_code, classes

    def _seed_books_step(self, tenant: Tenant, opts: dict, totals: dict):
        if opts['users_only']:
            self._info("Books: skipped (--users-only).", heading='Step 4/5')
            return

        files = discover_book_files()
        if not files:
            self.stdout.write(self.style.WARNING(
                "No book YAMLs found under fixtures/synthetic_books/. Skipping books step."
            ))
            return

        # Pick a school admin as the AuditModel.created_by for the book.
        from apps.accounts.models import User
        admin = User.objects.filter(tenant=tenant, role__name=Role.SCHOOL_ADMIN).first()

        result = seed_books(tenant, book_files=files, created_by=admin)
        totals['documents_created'] += result['documents_created']
        totals['documents_updated'] += result['documents_updated']
        for k in ('chapters', 'sections', 'topics', 'leaves', 'cross_refs'):
            totals[k] += result[k]

        self._info(
            f"Books: processed={result['books_processed']} "
            f"created={result['documents_created']} "
            f"updated={result['documents_updated']} "
            f"chapters={result['chapters']} sections={result['sections']} "
            f"topics={result['topics']} leaves={result['leaves']} "
            f"cross_refs={result['cross_refs']}",
            heading='Step 4/5',
        )

    def _embed_tenant_nodes(self, tenant: Tenant) -> int:
        """Embed every synthetic ContentNode for this tenant and upsert to ChromaDB."""
        from apps.service.models import ContentNode

        nodes = list(
            ContentNode.objects.filter(
                tenant=tenant,
                document__source_type='synthetic',
            ).exclude(content_plain='')
        )
        if not nodes:
            return 0

        try:
            from clients.embeddings import init_model
            from clients.vector_store import VectorStoreClient
        except ImportError as e:
            self.stdout.write(self.style.ERROR(f"Embeddings dependencies missing: {e}"))
            return 0

        init_model()  # idempotent
        vs = VectorStoreClient()
        collection = vs.get_or_create_collection(str(tenant.id), 'curriculum')

        # Chunk into batches of 64 to keep memory predictable
        batch_size = 64
        added_total = 0
        for start in range(0, len(nodes), batch_size):
            chunk = nodes[start:start + batch_size]
            documents = [n.content_plain for n in chunk]
            metadatas = [{
                'tenant_id': str(tenant.id),
                'document_id': n.document_id,
                'node_id': n.node_id,
                'node_type': n.node_type,
                'subject_id': n.subject_id,
                'difficulty': n.difficulty or '',
                'title': n.title,
            } for n in chunk]
            ids = [f"{tenant.id}-{n.document_id}-{n.node_id}" for n in chunk]
            # Delete-then-add gives idempotent upsert semantics (Chroma's
            # native upsert exists too but is on collection.upsert which
            # has identical effect via add+ids on PersistentClient)
            try:
                collection.delete(ids=ids)
            except Exception:
                pass
            added_total += vs.add_documents(collection, documents, metadatas=metadatas, ids=ids)

            # Track embedding ids on the ContentNodes so retrieval results
            # can be tied back to ORM rows easily.
            for n, eid in zip(chunk, ids):
                if n.embedding_id != eid:
                    n.embedding_id = eid
            ContentNode.objects.bulk_update(chunk, ['embedding_id'])

        return added_total

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _verify_roles_exist(self):
        missing = [r for r in (Role.STUDENT, Role.TEACHER, Role.SCHOOL_ADMIN) if not Role.objects.filter(name=r).exists()]
        if missing:
            raise CommandError(
                f"Required role(s) missing: {missing}. Run `python manage.py create_roles` first."
            )

    def _info(self, msg: str, heading: str | None = None):
        if heading:
            self.stdout.write(self.style.HTTP_INFO(f"[{heading}] {msg}"))
        else:
            self.stdout.write(f"          {msg}")

    def _print_summary(self, totals: dict, with_embeddings: bool):
        self.stdout.write(self.style.SUCCESS("\n=== Seed summary ==="))
        users = totals['users_created']
        users_total = users['school_admins'] + users['teachers'] + users['students']
        self.stdout.write(
            f"tenants={totals['tenants']} "
            f"users=+{users_total} "
            f"(school_admins=+{users['school_admins']} "
            f"teachers=+{users['teachers']} "
            f"students=+{users['students']}) "
        )
        self.stdout.write(
            f"subjects={totals['subjects']} "
            f"classes={totals['classes']} "
            f"class_subjects={totals['class_subjects']}"
        )
        self.stdout.write(
            f"books_created={totals['documents_created']} "
            f"books_updated={totals['documents_updated']} "
            f"chapters={totals['chapters']} "
            f"sections={totals['sections']} "
            f"topics={totals['topics']} "
            f"leaves={totals['leaves']} "
            f"cross_refs={totals['cross_refs']}"
        )
        if with_embeddings:
            self.stdout.write(f"embeddings_added={totals['embeddings_added']}")
        else:
            self.stdout.write("embeddings=skipped (use --with-embeddings to include)")
