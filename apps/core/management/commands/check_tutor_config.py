"""
Diagnose why the AI tutor might be returning "temporarily unavailable".

Usage:
    python manage.py check_tutor_config               # check config only
    python manage.py check_tutor_config --test        # also do a live LLM call

Prints:
  * All LLM-related AppSetting rows (key, is_active, masked value).
  * What `django.conf.settings` currently holds for each key after the
    admin-managed AppSetting overrides are freshly re-applied.
  * Optionally (`--test`): makes a real `LLMService.generate` call and
    reports the exact error class + message so you can fix it fast.

Never modifies data. Safe in any environment.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.core.models import AppSetting


# Keys the tutor cares about. (key, is_secret, critical)
#   critical=True  → if missing the tutor cannot answer → VERDICT red
#   critical=False → optional / has a sensible default → shown but not fatal
# `LLM_PROVIDER` and `ANTHROPIC_API_KEY` are tracked by the bootstrap
# registry but not consumed directly yet; included so they don't look
# like typos.
_CHECKED_KEYS = (
    ('OPENAI_API_KEY',     True,  True),
    ('OPENAI_BASE_URL',    False, False),
    ('OPENAI_MODEL_NAME',  False, False),
    ('LLM_PROVIDER',       False, False),
    ('ANTHROPIC_API_KEY',  True,  False),
    ('EMBEDDING_PROVIDER', False, False),
    ('EMBEDDER_API_URL',   False, False),
    ('EMBEDDER_API_KEY',   True,  False),
)


def _mask(value: str, is_secret: bool) -> str:
    """Return a printable representation — masked for secrets."""
    if not value:
        return '(empty)'
    if not is_secret:
        return value
    tail = value[-4:] if len(value) >= 8 else ''
    return f'****{tail}' if tail else '********'


class Command(BaseCommand):
    help = "Diagnose the AI tutor's runtime LLM / embedding config."

    def add_arguments(self, parser):
        parser.add_argument(
            '--test',
            action='store_true',
            help='Make a real LLM call with current settings and report the result.',
        )

    def handle(self, *args, **opts):
        out = self.stdout

        # Re-apply AppSetting overrides so we print the live state the
        # tutor will actually see on its next request.
        applied = AppSetting.apply_to_settings()
        out.write(f'Re-applied {applied} active AppSetting override(s).\n')

        # ------------------------------------------------------------------ AppSetting rows
        watched_keys = {k for k, _, _ in _CHECKED_KEYS}
        out.write(self.style.HTTP_INFO('\n== AppSetting rows (scanned for tutor keys) =='))
        rows = list(
            AppSetting.objects
            .filter(key__in=watched_keys)
            .order_by('key')
        )
        # Also include rows whose key *looks like* a tutor key but isn't an
        # exact match (case typos, whitespace in the key) — these are a
        # common reason for "I set it but nothing happens".
        lookalikes = [
            r for r in AppSetting.objects.all()
            if any(w.lower() in (r.key or '').lower() for w in ('openai', 'embedder', 'llm'))
            and r.key not in watched_keys
        ]
        if not rows and not lookalikes:
            out.write(self.style.WARNING(
                '  (no rows match tutor keys; run '
                '`python manage.py bootstrap_app_settings` first)'
            ))
        for row in rows:
            state = 'active  ' if row.is_active else 'INACTIVE'
            val = (row.value or '').strip()
            masked = _mask(val, row.is_secret)
            out.write(f'  [{state}] {row.key:<22} = {masked}  (category={row.category})')
            if row.key != row.key.strip():
                out.write(self.style.ERROR(
                    '            ! key has leading/trailing whitespace'
                ))
        for row in lookalikes:
            out.write(self.style.ERROR(
                f'  ! Row with non-matching key: "{row.key}" '
                f'(category={row.category}). Rename to one of: '
                f'{", ".join(sorted(watched_keys))}'
            ))

        # ------------------------------------------------------------------ settings state
        out.write(self.style.HTTP_INFO('\n== django.conf.settings (what the tutor sees) =='))
        missing_critical = []
        for key, is_secret, critical in _CHECKED_KEYS:
            value = getattr(settings, key, '') or ''
            if isinstance(value, str):
                value = value.strip()
            masked = _mask(str(value), is_secret)
            if not value:
                tag = self.style.ERROR('REQUIRED') if critical else self.style.NOTICE('optional ')
                out.write(f'  {key:<22} = {masked}   [{tag} not set]')
                if critical:
                    missing_critical.append(key)
            else:
                out.write(f'  {key:<22} = {masked}')

        # ------------------------------------------------------------------ verdict
        out.write('')
        if missing_critical:
            out.write(self.style.ERROR(
                'VERDICT: Tutor will refuse requests.\n'
                f'  Missing required key(s): {", ".join(missing_critical)}\n'
                '  Fix in /admin/core/appsetting/ — key must match exactly, '
                'Value non-empty, "Is active" ticked. Tutor re-reads the DB '
                'on every request, so no restart needed.'
            ))
            return
        else:
            base = getattr(settings, 'OPENAI_BASE_URL', '') or ''
            model = getattr(settings, 'OPENAI_MODEL_NAME', '') or ''
            out.write(self.style.SUCCESS(
                f'VERDICT: Tutor is configured. Will call {model or "(default model)"} '
                f'at {base or "(default OpenAI URL)"}.'
            ))

        # ------------------------------------------------------------------ live LLM test
        if opts.get('test'):
            self._test_llm_call()

    # ---------------------------------------------------------------- live test

    def _test_llm_call(self):
        """Make a minimal LLM call and print what actually comes back.

        This is the fastest way to see whether a "temporarily unavailable"
        message in the UI is caused by a config problem or by an upstream
        failure (wrong base_url path, invalid key for that proxy,
        unsupported model name, network block, etc.).
        """
        out = self.stdout
        out.write(self.style.HTTP_INFO('\n== Live LLM test =='))

        try:
            from clients.llm import LLMService
        except Exception as exc:
            out.write(self.style.ERROR(f'  Could not import LLMService: {exc}'))
            return

        llm = LLMService()
        out.write(f'  base_url = {llm._base_url}')
        out.write(f'  model    = {llm.model}')
        out.write(f'  api_key  = {_mask(llm._api_key, True)}')
        out.write('  Sending a tiny test prompt ("Reply with just the word: pong")...')

        try:
            reply = llm.generate(
                prompt='Reply with just the word: pong',
                system='You are a health-check bot. Respond with one word only.',
                max_tokens=8,
                temperature=0.0,
            )
        except Exception as exc:
            out.write(self.style.ERROR(f'\n  FAIL: {type(exc).__name__}: {exc}'))
            out.write(self.style.ERROR(
                '\n  This is the same error the tutor sees when a student asks a '
                'question. Common causes:\n'
                '    * base_url missing the "/v1" suffix (OpenAI-compatible proxies often need it).\n'
                '    * api_key not accepted by the proxy — regenerate or re-paste.\n'
                '    * model name not recognised by the proxy — try listing available models.\n'
                '    * proxy blocks non-HTTPS or requires an extra header.'
            ))
            return

        reply_snippet = (reply or '').strip().replace('\n', ' ')
        if len(reply_snippet) > 200:
            reply_snippet = reply_snippet[:197] + '...'
        out.write(self.style.SUCCESS(f'\n  OK -> "{reply_snippet}"'))
        out.write(self.style.SUCCESS(
            '  The LLM endpoint accepts your key and responds. If the tutor '
            'still shows an error, re-run the request — retrieval or embedding '
            'may be the culprit; check the server log for the full stack trace.'
        ))
