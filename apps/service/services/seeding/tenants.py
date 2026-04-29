"""
Tenant seeding for synthetic data.

Creates or reuses demo tenants. Idempotent: keyed on slug.
"""

from typing import Iterable, List

from apps.accounts.models import Tenant


DEFAULT_TENANTS = [
    {
        'slug': 'springfield',
        'name': 'Springfield Public School',
        'primary_color': '#4F46E5',
        'email': 'admin@springfield.test',
        'subscription_tier': 'premium',
        'max_students': 500,
        'max_teachers': 50,
    },
    {
        'slug': 'riverside',
        'name': 'Riverside International Academy',
        'primary_color': '#10B981',
        'email': 'admin@riverside.test',
        'subscription_tier': 'premium',
        'max_students': 500,
        'max_teachers': 50,
    },
]


def seed_tenants(slugs: Iterable[str] = None) -> List[Tenant]:
    """
    Create or reuse demo tenants for the given slugs.

    If `slugs` is None or empty, seeds the default two tenants
    (`springfield`, `riverside`).
    Custom slugs not in DEFAULT_TENANTS get sensible auto-generated names.

    Returns the list of Tenant rows in input order.
    """
    requested = list(slugs) if slugs else [t['slug'] for t in DEFAULT_TENANTS]
    defaults_by_slug = {t['slug']: t for t in DEFAULT_TENANTS}

    tenants: List[Tenant] = []
    for slug in requested:
        spec = defaults_by_slug.get(slug, {
            'slug': slug,
            'name': slug.replace('-', ' ').replace('_', ' ').title() + ' School',
            'primary_color': '#6366F1',
            'email': f'admin@{slug}.test',
            'subscription_tier': 'free',
            'max_students': 200,
            'max_teachers': 20,
        })
        tenant, _ = Tenant.objects.get_or_create(
            slug=spec['slug'],
            defaults={
                'name': spec['name'],
                'primary_color': spec['primary_color'],
                'email': spec.get('email', ''),
                'subscription_tier': spec.get('subscription_tier', 'free'),
                'max_students': spec.get('max_students', 100),
                'max_teachers': spec.get('max_teachers', 10),
                'is_active': True,
            },
        )
        tenants.append(tenant)
    return tenants


def reset_tenant_synthetic_data(tenant: Tenant) -> dict:
    """
    Delete only synthetic rows scoped to this tenant.

    Removes Documents (+ cascading ContentNodes, Assets, ContentCrossRefs)
    where `source_type='synthetic'`. Leaves users, classes, subjects intact
    so a `--books-only --reset` workflow is possible.
    """
    from apps.service.models import Document

    qs = Document.objects.filter(tenant=tenant, source_type='synthetic')
    count = qs.count()
    qs.delete()
    return {'documents_deleted': count}
