"""
Synthetic data seeding services.

Each module is independently runnable so callers can re-seed users without
rebuilding books, etc. All seeders are idempotent and tenant-scoped.

Module map
----------
- tenants.py      Demo tenants (`springfield`, `riverside`).
- users.py        School admin + teachers + students per tenant (faker-backed).
- classes.py      Subjects + Classes + ClassSubject mappings per tenant.
- books.py        YAML books -> Document + ContentNode tree + cross-refs.
- submissions.py  (Phase 4 stub) student submissions and grades.
"""

from .tenants import seed_tenants
from .users import seed_users
from .classes import seed_classes
from .books import seed_books

__all__ = ['seed_tenants', 'seed_users', 'seed_classes', 'seed_books']
