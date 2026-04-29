"""Core app configuration.

`ready()` runs once per process at server startup. We use it to push
admin-managed `AppSetting` rows into `django.conf.settings` so values
edited in the Django admin transparently override the `.env` file on
the next restart.
"""

import logging
import sys
import warnings

from django.apps import AppConfig

logger = logging.getLogger(__name__)


# Management commands where we should NOT touch the AppSetting table:
# either it doesn't exist yet (makemigrations/migrate), or the DB is
# being inspected (sqlmigrate/showmigrations), or it's a static-files
# operation that has nothing to do with settings.
_SKIP_COMMANDS = frozenset({
    'makemigrations', 'migrate', 'showmigrations', 'sqlmigrate',
    'flush', 'sqlflush', 'collectstatic', 'compilemessages',
})


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = 'Core Infrastructure'

    def ready(self) -> None:
        if len(sys.argv) > 1 and sys.argv[1] in _SKIP_COMMANDS:
            return

        from django.db.utils import OperationalError, ProgrammingError

        try:
            from apps.core.models.app_setting import AppSetting
            # Suppress Django's "Accessing the database during app
            # initialization is discouraged" RuntimeWarning. Our use
            # case is exactly that: load runtime settings before the
            # first request. The warning is cosmetic in our case
            # because by the time `ready()` runs, the DB connection
            # has finished setup for non-migration commands.
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', RuntimeWarning)
                applied = AppSetting.apply_to_settings()
        except (OperationalError, ProgrammingError) as exc:
            logger.info(
                'AppSetting overrides skipped (table not ready yet): %s',
                exc.__class__.__name__,
            )
            return

        if applied:
            logger.info(
                'Applied %d AppSetting override(s) to django.conf.settings.',
                applied,
            )
