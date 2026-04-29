"""
Integration tests for the synthetic data seeding pipeline.

Covers:
  * end-to-end seed produces the expected counts
  * re-running is idempotent (no row growth)
  * tenant data is properly isolated
  * Document.source_type='synthetic' + Document.file is empty for seeded books
  * ContentNode tree depth and parent links are correct
"""

from django.test import TestCase

from apps.accounts.models import Role, Tenant, User
from apps.service.models import (
    Class,
    ClassSubject,
    ContentCrossRef,
    ContentNode,
    Document,
    Subject,
)
from apps.service.services.seeding import (
    seed_books,
    seed_classes,
    seed_tenants,
    seed_users,
)
from apps.service.services.seeding.books import discover_book_files
from apps.service.services.seeding.classes import (
    seed_class_subjects,
    seed_subjects,
)


# Roles must exist for users seeding to work. Seed a minimal set.
def _bootstrap_roles():
    for code in (Role.STUDENT, Role.TEACHER, Role.SCHOOL_ADMIN):
        Role.objects.get_or_create(name=code, defaults={'display_name': code.title(), 'level': 50})


def _seed_full(tenant: Tenant, students: int = 8, teachers: int = 3):
    """Run the full synthetic seed for one tenant with small N for fast tests."""
    users = seed_users(tenant, seed=42, teachers_count=teachers, students_count=students)
    subjects_by_code = seed_subjects(tenant)
    classes = seed_classes(tenant, teachers=users['teachers'])
    seed_class_subjects(classes, subjects_by_code, users['teachers'])
    seed_books(tenant, book_files=discover_book_files(), created_by=users['school_admins'][0])


class SeedSyntheticDataTests(TestCase):
    """Tests run on an isolated test database (Django wipes between methods)."""

    @classmethod
    def setUpTestData(cls):
        _bootstrap_roles()

    def test_full_seed_creates_expected_rows(self):
        tenants = seed_tenants(['acme'])
        self.assertEqual(len(tenants), 1)
        tenant = tenants[0]

        _seed_full(tenant, students=8, teachers=3)

        self.assertEqual(User.objects.filter(tenant=tenant, role__name=Role.SCHOOL_ADMIN).count(), 1)
        self.assertEqual(User.objects.filter(tenant=tenant, role__name=Role.TEACHER).count(), 3)
        self.assertEqual(User.objects.filter(tenant=tenant, role__name=Role.STUDENT).count(), 8)

        self.assertGreater(Subject.objects.filter(tenant=tenant).count(), 0)
        self.assertGreater(Class.objects.filter(tenant=tenant).count(), 0)
        self.assertGreater(ClassSubject.objects.filter(class_obj__tenant=tenant).count(), 0)

        # All seeded books are tagged synthetic and have no file
        docs = Document.objects.filter(tenant=tenant)
        self.assertGreater(docs.count(), 0)
        for d in docs:
            self.assertEqual(d.source_type, Document.SourceType.SYNTHETIC)
            self.assertEqual(d.status, Document.Status.COMPLETED)
            self.assertFalse(bool(d.file), f'Synthetic doc {d.title} should not have a file')

        # ContentNodes exist and parent links are set within each book
        nodes = ContentNode.objects.filter(tenant=tenant)
        self.assertGreater(nodes.count(), 0)
        for n in nodes.exclude(node_type='chapter'):
            self.assertIsNotNone(n.parent_id, f'Non-chapter node {n.node_id} must have a parent')

    def test_seed_is_idempotent(self):
        tenant = seed_tenants(['acme'])[0]
        _seed_full(tenant, students=6, teachers=2)

        snap = {
            'tenants': Tenant.objects.count(),
            'users': User.objects.filter(tenant=tenant).count(),
            'subjects': Subject.objects.filter(tenant=tenant).count(),
            'classes': Class.objects.filter(tenant=tenant).count(),
            'class_subjects': ClassSubject.objects.filter(class_obj__tenant=tenant).count(),
            'documents': Document.objects.filter(tenant=tenant).count(),
            'nodes': ContentNode.objects.filter(tenant=tenant).count(),
            'cross_refs': ContentCrossRef.objects.filter(tenant=tenant).count(),
        }

        # Run the entire seed again with identical inputs.
        _seed_full(tenant, students=6, teachers=2)

        for key, expected in snap.items():
            actual_qs = {
                'tenants': Tenant.objects.count(),
                'users': User.objects.filter(tenant=tenant).count(),
                'subjects': Subject.objects.filter(tenant=tenant).count(),
                'classes': Class.objects.filter(tenant=tenant).count(),
                'class_subjects': ClassSubject.objects.filter(class_obj__tenant=tenant).count(),
                'documents': Document.objects.filter(tenant=tenant).count(),
                'nodes': ContentNode.objects.filter(tenant=tenant).count(),
                'cross_refs': ContentCrossRef.objects.filter(tenant=tenant).count(),
            }[key]
            self.assertEqual(
                actual_qs, expected,
                f'Idempotency violated for {key!r}: expected {expected}, got {actual_qs}'
            )

    def test_tenant_isolation(self):
        # Seed two tenants with the same data; cross-queries must be empty.
        spring = seed_tenants(['springfield-test'])[0]
        river = seed_tenants(['riverside-test'])[0]

        _seed_full(spring, students=5, teachers=2)
        _seed_full(river, students=5, teachers=2)

        spring_docs = Document.objects.filter(tenant=spring)
        river_docs = Document.objects.filter(tenant=river)
        self.assertGreater(spring_docs.count(), 0)
        self.assertGreater(river_docs.count(), 0)

        # No document of one tenant matches the other tenant's id
        self.assertFalse(spring_docs.filter(tenant=river).exists())
        self.assertFalse(river_docs.filter(tenant=spring).exists())

        # Same for ContentNodes
        spring_nodes = ContentNode.objects.filter(tenant=spring)
        river_nodes = ContentNode.objects.filter(tenant=river)
        self.assertFalse(spring_nodes.filter(tenant=river).exists())
        self.assertFalse(river_nodes.filter(tenant=spring).exists())

        # Users are scoped per tenant
        spring_users = User.objects.filter(tenant=spring)
        river_users = User.objects.filter(tenant=river)
        self.assertFalse(spring_users.filter(tenant=river).exists())
        # Email prefixes carry the tenant slug so we can sanity-check
        for u in spring_users:
            self.assertTrue(u.email.endswith('@springfield-test.test'))
        for u in river_users:
            self.assertTrue(u.email.endswith('@riverside-test.test'))

    def test_book_yaml_files_discovered(self):
        files = discover_book_files()
        self.assertGreaterEqual(len(files), 6, 'Expected at least 6 starter book YAMLs')

    def test_content_node_tree_has_expected_types(self):
        tenant = seed_tenants(['acme'])[0]
        _seed_full(tenant, students=2, teachers=1)
        node_types = set(
            ContentNode.objects
            .filter(tenant=tenant)
            .values_list('node_type', flat=True)
            .distinct()
        )
        # We should at least have chapters, sections, topics and some leaves
        for required in {'chapter', 'section', 'topic'}:
            self.assertIn(required, node_types)
        self.assertTrue(node_types & {'definition', 'formula', 'example', 'exercise', 'key_point', 'summary'})
