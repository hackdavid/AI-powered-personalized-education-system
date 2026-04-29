"""Core app views - infrastructure-level only.

Domain template views (home, dashboards) live in apps.web.views.
"""

from django.db import connection
from django.http import JsonResponse
from django.utils import timezone


def health_check(request):
    """JSON health endpoint. Extend with vector store / LLM probes as they land."""
    checks = {}

    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        checks['database'] = {'healthy': True, 'message': 'Database connection OK'}
    except Exception as exc:  # noqa: BLE001
        checks['database'] = {'healthy': False, 'message': str(exc)}

    all_healthy = all(c['healthy'] for c in checks.values())
    return JsonResponse(
        {
            'status': 'healthy' if all_healthy else 'unhealthy',
            'checks': checks,
            'timestamp': timezone.now().isoformat(),
        },
        status=200 if all_healthy else 503,
    )
