"""Seed the starter Badge catalog and optionally backfill qualifying EarnedBadges.

Usage
-----
    # Install / refresh the 10 starter badges (idempotent via update_or_create on `code`).
    python manage.py seed_badges

    # Also run the badge engine against every existing student so anyone
    # already qualified gets their badges retroactively.
    python manage.py seed_badges --backfill

    # Scope backfill to one tenant.
    python manage.py seed_badges --backfill --tenant springfield
"""

from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.service.models import Badge, EarnedBadge
from apps.service.services.badges import STARTER_BADGES, evaluate_and_award


class Command(BaseCommand):
    help = 'Install the starter Badge catalog and optionally backfill earned badges.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--backfill', action='store_true',
            help='Run the badge engine against every existing student.',
        )
        parser.add_argument(
            '--tenant', default=None,
            help='Limit --backfill to students of one tenant (by slug).',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Print what would happen; make no changes.',
        )

    def handle(self, *args, **options):
        dry = options['dry_run']
        created_badges = 0
        updated_badges = 0

        # ---- 1. Install / refresh catalog ---------------------------------
        for spec in STARTER_BADGES:
            code = spec['code']
            defaults = {k: v for k, v in spec.items() if k != 'code'}
            if dry:
                existing = Badge.objects.filter(code=code).first()
                if existing:
                    updated_badges += 1
                else:
                    created_badges += 1
                continue

            _, created = Badge.objects.update_or_create(
                code=code, defaults=defaults,
            )
            if created:
                created_badges += 1
            else:
                updated_badges += 1

        self.stdout.write(self.style.SUCCESS(
            f'Badges: {created_badges} created, {updated_badges} refreshed '
            f'({len(STARTER_BADGES)} total in catalog).'
        ))

        # ---- 2. Optional backfill -----------------------------------------
        if not options['backfill']:
            return

        qs = User.objects.filter(role__name='student', is_active=True)
        if options['tenant']:
            qs = qs.filter(tenant__slug=options['tenant'])

        total_students = qs.count()
        awarded_count = 0
        self.stdout.write(
            f'Backfilling badges for {total_students} students'
            + (f' in tenant {options["tenant"]}' if options['tenant'] else '')
            + '...'
        )

        if dry:
            self.stdout.write('[dry-run] would iterate students and call evaluate_and_award.')
            return

        for student in qs.iterator():
            newly = evaluate_and_award(student, event_type='backfill')
            awarded_count += len(newly)

        self.stdout.write(self.style.SUCCESS(
            f'Backfill complete — {awarded_count} EarnedBadge rows written '
            f'across {total_students} students.'
        ))
        self.stdout.write(
            f'Total EarnedBadge rows in DB now: {EarnedBadge.objects.count()}'
        )
