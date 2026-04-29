"""
Tests for the runtime-overridable AppSetting layer.

Covers:
  * model basics: __str__, masked_value semantics
  * apply_to_settings(): only active rows propagate; inactive ones leave
    the existing django.conf.settings value alone
  * cross-process behaviour matches: re-running apply_to_settings() picks
    up DB changes (mimics what server restart does)
  * bootstrap command: creates expected rows, is idempotent, respects
    --include-secrets, masks secret values when omitted
"""

from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.core.models import AppSetting


class AppSettingModelTests(TestCase):

    def test_str_returns_key_and_category(self):
        s = AppSetting.objects.create(key='OPENAI_API_KEY', category='llm', value='sk-x')
        self.assertIn('OPENAI_API_KEY', str(s))
        self.assertIn('LLM', str(s))

    def test_masked_value_for_non_secret_returns_full_value(self):
        s = AppSetting(key='OPENAI_BASE_URL', value='https://api.openai.com/v1', is_secret=False)
        self.assertEqual(s.masked_value, 'https://api.openai.com/v1')

    def test_masked_value_for_short_secret_is_dots_only(self):
        s = AppSetting(key='OPENAI_API_KEY', value='abcd', is_secret=True)
        self.assertEqual(s.masked_value, '••••••••')

    def test_masked_value_for_long_secret_shows_last_four(self):
        s = AppSetting(key='OPENAI_API_KEY', value='sk-abcdef1234ZxYw', is_secret=True)
        self.assertEqual(s.masked_value, '••••ZxYw')

    def test_masked_value_for_empty_value_is_empty(self):
        s = AppSetting(key='OPENAI_API_KEY', value='', is_secret=True)
        self.assertEqual(s.masked_value, '')


class ApplyToSettingsTests(TestCase):
    """The DB → settings hand-off used by CoreConfig.ready()."""

    @override_settings(OPENAI_BASE_URL='https://from-env.test/v1')
    def test_active_row_overrides_settings_value(self):
        AppSetting.objects.create(
            key='OPENAI_BASE_URL', value='https://from-db.test/v1',
            category='llm', is_active=True,
        )
        applied = AppSetting.apply_to_settings()

        self.assertEqual(applied, 1)
        self.assertEqual(settings.OPENAI_BASE_URL, 'https://from-db.test/v1')

    @override_settings(OPENAI_BASE_URL='https://from-env.test/v1')
    def test_inactive_row_leaves_settings_unchanged(self):
        AppSetting.objects.create(
            key='OPENAI_BASE_URL', value='https://from-db.test/v1',
            category='llm', is_active=False,
        )
        applied = AppSetting.apply_to_settings()

        self.assertEqual(applied, 0)
        # The .env-derived value (faked via override_settings) is intact
        self.assertEqual(settings.OPENAI_BASE_URL, 'https://from-env.test/v1')

    @override_settings(OPENAI_BASE_URL='https://from-env.test/v1')
    def test_changing_db_then_reapply_picks_up_new_value(self):
        """Mimics 'edit in admin -> restart server -> new value visible'."""
        row = AppSetting.objects.create(
            key='OPENAI_BASE_URL', value='https://first.test',
            category='llm', is_active=True,
        )
        AppSetting.apply_to_settings()
        self.assertEqual(settings.OPENAI_BASE_URL, 'https://first.test')

        # User edits the value in admin
        row.value = 'https://second.test'
        row.save()

        # On restart, ready() re-runs apply_to_settings()
        AppSetting.apply_to_settings()
        self.assertEqual(settings.OPENAI_BASE_URL, 'https://second.test')

    @override_settings(EMBEDDER_API_KEY='env-default')
    def test_multiple_active_rows_all_propagate(self):
        AppSetting.objects.create(
            key='EMBEDDER_API_KEY', value='from-db-1', category='embedding', is_active=True,
        )
        AppSetting.objects.create(
            key='EMBEDDER_API_URL', value='https://from-db-2.test', category='embedding', is_active=True,
        )
        applied = AppSetting.apply_to_settings()

        self.assertEqual(applied, 2)
        self.assertEqual(settings.EMBEDDER_API_KEY, 'from-db-1')
        self.assertEqual(settings.EMBEDDER_API_URL, 'https://from-db-2.test')


class BootstrapCommandTests(TestCase):

    def _run(self, *args):
        out = StringIO()
        call_command('bootstrap_app_settings', *args, stdout=out)
        return out.getvalue()

    @override_settings(
        OPENAI_API_KEY='sk-test-from-env',
        OPENAI_BASE_URL='https://api.openai.com/v1',
        OPENAI_MODEL_NAME='gpt-4',
        ANTHROPIC_API_KEY='',
        LLM_PROVIDER='openai',
        EMBEDDING_PROVIDER='remote',
        EMBEDDER_API_URL='https://example.test',
        EMBEDDER_API_KEY='emb-test',
        EMBEDDING_MODEL_NAME='all-MiniLM-L6-v2',
        VECTOR_STORE_TYPE='pgvector',
    )
    def test_first_run_creates_all_known_keys(self):
        output = self._run()
        self.assertIn('Bootstrap complete', output)
        self.assertGreaterEqual(AppSetting.objects.count(), 10)

        # Public keys carry their .env value
        url = AppSetting.objects.get(key='EMBEDDER_API_URL')
        self.assertEqual(url.value, 'https://example.test')
        self.assertTrue(url.is_active)

        # Secrets are seeded EMPTY (and inactive) without --include-secrets
        secret = AppSetting.objects.get(key='OPENAI_API_KEY')
        self.assertEqual(secret.value, '')
        self.assertFalse(secret.is_active)
        self.assertTrue(secret.is_secret)

    @override_settings(
        OPENAI_API_KEY='sk-test-from-env',
        EMBEDDER_API_KEY='emb-test',
    )
    def test_include_secrets_copies_secret_values(self):
        output = self._run('--include-secrets')
        self.assertIn('Bootstrap complete', output)
        self.assertEqual(
            AppSetting.objects.get(key='OPENAI_API_KEY').value,
            'sk-test-from-env',
        )
        self.assertTrue(AppSetting.objects.get(key='OPENAI_API_KEY').is_active)

    @override_settings(EMBEDDER_API_URL='https://example.test')
    def test_rerun_is_idempotent(self):
        self._run()
        first_count = AppSetting.objects.count()
        first_url = AppSetting.objects.get(key='EMBEDDER_API_URL').value

        # User edits a value via admin
        row = AppSetting.objects.get(key='EMBEDDER_API_URL')
        row.value = 'https://edited-by-admin.test'
        row.save()

        # Re-running bootstrap MUST NOT clobber the curated value
        self._run()
        self.assertEqual(AppSetting.objects.count(), first_count)
        self.assertEqual(
            AppSetting.objects.get(key='EMBEDDER_API_URL').value,
            'https://edited-by-admin.test',
        )
        self.assertNotEqual(first_url, 'https://edited-by-admin.test')
