"""Ensure every existing student user has a StudentProfile row."""

from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.service.models.student_profile import StudentProfile


class Command(BaseCommand):
    help = 'Create StudentProfile rows for any existing student users missing one.'

    def handle(self, *args, **options):
        qs = User.objects.filter(role__name='student', is_active=True)
        created_count = 0
        for user in qs.iterator():
            _, created = StudentProfile.objects.get_or_create(
                student=user,
                defaults={'onboarding_complete': False},
            )
            if created:
                created_count += 1
        total = qs.count()
        self.stdout.write(self.style.SUCCESS(
            f'Backfilled {created_count} new StudentProfile rows '
            f'(total students: {total}).'
        ))
