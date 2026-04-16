"""
Request Logging Middleware - Logs all requests with correlation IDs.
"""

import logging
import time
import uuid
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(MiddlewareMixin):
    """
    Middleware to log all incoming requests and responses with metadata.
    Adds correlation ID for request tracing.
    """

    def process_request(self, request):
        """Log incoming request and add correlation ID."""
        # Generate correlation ID for request tracking
        correlation_id = str(uuid.uuid4())
        request.correlation_id = correlation_id

        # Record request start time
        request.start_time = time.time()

        # Log request
        logger.info(
            "Request started",
            extra={
                'correlation_id': correlation_id,
                'method': request.method,
                'path': request.path,
                'user': str(request.user) if request.user.is_authenticated else 'Anonymous',
                'tenant': request.tenant.name if hasattr(request, 'tenant') and request.tenant else None,
                'ip_address': self._get_client_ip(request),
            }
        )

    def process_response(self, request, response):
        """Log response with timing information."""
        if hasattr(request, 'start_time'):
            duration = time.time() - request.start_time

            logger.info(
                "Request completed",
                extra={
                    'correlation_id': getattr(request, 'correlation_id', 'unknown'),
                    'method': request.method,
                    'path': request.path,
                    'status_code': response.status_code,
                    'duration_ms': round(duration * 1000, 2),
                }
            )

        return response

    def process_exception(self, request, exception):
        """Log exceptions that occur during request processing."""
        logger.error(
            "Request exception",
            extra={
                'correlation_id': getattr(request, 'correlation_id', 'unknown'),
                'method': request.method,
                'path': request.path,
                'exception': str(exception),
                'exception_type': type(exception).__name__,
            },
            exc_info=True
        )

    @staticmethod
    def _get_client_ip(request):
        """Extract client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
