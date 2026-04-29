"""
Bootstrap AppSetting rows from the current `.env` / `django.conf.settings`.

Run once after the AppSetting migration lands. Creates a DB row for every
known overridable key, copying the current value (from `.env` or the
default in `config/settings/base.py`) so the admin can edit them without
losing what's already configured.

Idempotent:
  * If a row already exists for a key, we skip it (never overwrite a value
    you've already curated in admin).
  * Re-running adds new keys without touching existing ones.

Flags:
  --reset           Delete all existing AppSetting rows first. Destructive.
                    Useful only when the registry below has changed and you
                    want a clean re-seed in dev. Asks for confirmation.
  --include-secrets Without this, secret keys are seeded with an EMPTY
                    value so a `.env`-leak doesn't propagate into the DB.
                    Pass this flag if you intentionally want to copy them.
"""

from typing import Iterable, NamedTuple

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.core.models import AppSetting


class _Spec(NamedTuple):
    key: str
    category: str
    is_secret: bool
    description: str


# Single source of truth for which keys can be runtime-overridden.
# Add new entries here when you want a key to appear in the admin.
REGISTRY: tuple[_Spec, ...] = (
    # ---- LLM ----
    _Spec('OPENAI_API_KEY', AppSetting.Category.LLM, True,
          'OpenAI / OpenAI-compatible API key. Empty value = stub mode in tutor.'),
    _Spec('OPENAI_BASE_URL', AppSetting.Category.LLM, False,
          'Base URL for the OpenAI-compatible endpoint (Azure / Ollama / OpenAI).'),
    _Spec('OPENAI_MODEL_NAME', AppSetting.Category.LLM, False,
          'Default chat model (e.g. gpt-4o-mini, gpt-4).'),
    _Spec('ANTHROPIC_API_KEY', AppSetting.Category.LLM, True,
          'Optional Anthropic API key (currently unused).'),
    _Spec('LLM_PROVIDER', AppSetting.Category.LLM, False,
          'Active LLM provider switch (currently always "openai").'),

    # ---- Embedding ----
    _Spec('EMBEDDING_PROVIDER', AppSetting.Category.EMBEDDING, False,
          'Embedding provider: "remote" (HF Space) or "local".'),
    _Spec('EMBEDDER_API_URL', AppSetting.Category.EMBEDDING, False,
          'Base URL of the eduai-embedder HuggingFace Space.'),
    _Spec('EMBEDDER_API_KEY', AppSetting.Category.EMBEDDING, True,
          'Shared secret matching the embedder Space\'s EMBEDDER_API_KEY.'),
    _Spec('EMBEDDING_MODEL_NAME', AppSetting.Category.EMBEDDING, False,
          'sentence-transformers model id (used by local provider only).'),

    # ---- Vector store ----
    _Spec('VECTOR_STORE_TYPE', AppSetting.Category.VECTOR_STORE, False,
          'Vector backend identifier — currently only "pgvector".'),
)


class Command(BaseCommand):
    help = 'Seed AppSetting rows from current settings / .env (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete all AppSetting rows first. Destructive.',
        )
        parser.add_argument(
            '--include-secrets',
            action='store_true',
            help='Copy secret values from .env into the new rows. Off by default.',
        )

    def handle(self, *args, **opts):
        if opts['reset']:
            self._confirm_reset()
            deleted, _ = AppSetting.objects.all().delete()
            self.stdout.write(self.style.WARNING(f'Reset: deleted {deleted} row(s).'))

        created, skipped = self._seed(REGISTRY, include_secrets=opts['include_secrets'])

        self.stdout.write(self.style.SUCCESS(
            f'Bootstrap complete: created={created} skipped={skipped} '
            f'total={AppSetting.objects.count()}'
        ))
        if not opts['include_secrets']:
            blanks = [k for k, _, secret, _ in REGISTRY if secret]
            self.stdout.write(
                'Note: secret keys were seeded with an empty value '
                f'({", ".join(blanks)}). Set them via /admin/core/appsetting/, '
                'then restart the server.'
            )

    # ------------------------------------------------------------------ helpers

    def _confirm_reset(self) -> None:
        if AppSetting.objects.exists():
            answer = input(
                'This will delete all existing AppSetting rows. '
                'Type "yes" to continue: '
            )
            if answer.strip().lower() != 'yes':
                raise CommandError('Aborted.')

    def _seed(self, specs: Iterable[_Spec], include_secrets: bool) -> tuple[int, int]:
        created = skipped = 0
        for spec in specs:
            if AppSetting.objects.filter(key=spec.key).exists():
                skipped += 1
                continue

            if spec.is_secret and not include_secrets:
                value = ''
            else:
                value = str(getattr(settings, spec.key, '') or '')

            AppSetting.objects.create(
                key=spec.key,
                value=value,
                category=spec.category,
                description=spec.description,
                is_secret=spec.is_secret,
                is_active=bool(value),  # only activate rows we have a value for
            )
            created += 1
            label = '(secret, blank)' if (spec.is_secret and not value) else ''
            self.stdout.write(f'  + {spec.key} {label}'.rstrip())

        return created, skipped
