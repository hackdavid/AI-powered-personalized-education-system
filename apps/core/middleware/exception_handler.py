"""
Exception Handler Middleware - Catches and handles exceptions globally.
"""

import logging
from django.http import JsonResponse
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class ExceptionHandlerMiddleware(MiddlewareMixin):
    """
    Global exception handler middleware.
    Catches all unhandled exceptions and returns standardized error responses.
    """

    def process_exception(self, request, exception):
        """Handle exceptions and return appropriate error response."""
        correlation_id = getattr(request, 'correlation_id', 'unknown')

        # Log the exception
        logger.error(
            f"Unhandled exception: {type(exception).__name__}",
            extra={
                'correlation_id': correlation_id,
                'path': request.path,
                'exception': str(exception),
            },
            exc_info=True
        )

        # Determine if this is an API request
        is_api = request.path.startswith('/api/') or request.headers.get('Accept') == 'application/json'

        if is_api:
            # Return JSON error response
            error_data = {
                'success': False,
                'message': 'An error occurred while processing your request.',
                'correlation_id': correlation_id,
            }

            # Include exception details in debug mode
            if settings.DEBUG:
                error_data['error'] = str(exception)
                error_data['error_type'] = type(exception).__name__

            return JsonResponse(error_data, status=500)

        # For non-API requests, let Django's default handler take over
        # (will render 500.html template)
        return None
