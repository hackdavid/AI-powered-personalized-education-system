"""
AppSetting — runtime-editable configuration backed by the database.

Lets a single admin manage values like API keys / external URLs through
Django admin without sharing them with the rest of the team. At server
startup `apps.core.apps.CoreConfig.ready()` reads every active row and
applies it to `django.conf.settings` via `setattr`. Existing code that
already does `from django.conf import settings; settings.OPENAI_API_KEY`
transparently gets the DB-overridden value.

Constraints:
  * String values only. The override is `setattr(settings, key, value)`.
    Don't put booleans / integers here — keep DJANGO_DEBUG, DEBUG-style
    flags in `.env` where python-decouple casts them at import time.
  * To change a value, edit it in admin then restart the server.
  * `.env` (read by `config()` at import time) is the fallback for any
    key without an active AppSetting row.
"""

from django.conf import settings
from django.db import models

from apps.core.models.base import AuditModel


class AppSetting(AuditModel):
    """A single runtime-overridable Django setting.

    `key` matches a Django settings attribute name (e.g. `OPENAI_API_KEY`).
    `value` is what gets written to `settings.<key>` at startup.
    """

    class Category(models.TextChoices):
        LLM = 'llm', 'LLM'
        EMBEDDING = 'embedding', 'Embedding'
        VECTOR_STORE = 'vector_store', 'Vector store'
        TUTORING = 'tutoring', 'Tutoring'
        PLATFORM = 'platform', 'Platform'
        OTHER = 'other', 'Other'

    key = models.CharField(
        max_length=128,
        unique=True,
        db_index=True,
        help_text='Django settings attribute name. Must match exactly (case-sensitive).',
    )
    value = models.TextField(
        blank=True,
        help_text='String value applied to django.conf.settings at server startup.',
    )
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.OTHER,
        db_index=True,
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        help_text='One-line note for the admin: where this is used / what it does.',
    )
    is_secret = models.BooleanField(
        default=False,
        help_text='When true, the value is masked in admin list views.',
    )
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text='If false, the row is ignored at startup and the .env fallback is used.',
    )

    class Meta:
        verbose_name = 'App setting'
        verbose_name_plural = 'App settings'
        ordering = ['category', 'key']
        indexes = [
            models.Index(fields=['is_active', 'category']),
        ]

    def __str__(self) -> str:
        return f'{self.key} ({self.get_category_display()})'

    @property
    def masked_value(self) -> str:
        """Display-friendly value: full text for non-secrets, masked for secrets."""
        if not self.value:
            return ''
        if not self.is_secret:
            return self.value
        # Show only the last 4 characters of secrets, padded with dots.
        tail = self.value[-4:] if len(self.value) >= 8 else ''
        return f'••••{tail}' if tail else '••••••••'

    @classmethod
    def apply_to_settings(cls) -> int:
        """Push every active row into django.conf.settings. Returns count applied.

        Called from `CoreConfig.ready()` at startup AND from the tutor pipeline
        at request time (so admin edits don't require a restart). Wrapped in a
        try/except by the caller so that a missing table (first migration) or
        an unreachable DB doesn't crash startup — we silently fall back to
        whatever `.env` / `settings.py` already provides.

        Values are whitespace-stripped on the way in. Copy-paste from the
        admin UI often carries trailing spaces / newlines that would
        otherwise sail through and produce a 401 at LLM-call time.
        """
        applied = 0
        for row in cls.objects.filter(is_active=True).only('key', 'value'):
            value = (row.value or '').strip()
            setattr(settings, row.key, value)
            applied += 1
        return applied
