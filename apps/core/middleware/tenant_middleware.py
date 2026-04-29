"""
Tenant Middleware - Extracts and sets the current tenant for multi-tenancy.
"""

import logging
from django.utils.deprecation import MiddlewareMixin
from apps.accounts.models import Tenant

logger = logging.getLogger(__name__)


class TenantMiddleware(MiddlewareMixin):
    """
    Middleware to extract tenant from subdomain or user and set it on the request.

    Tenant resolution priority:
    1. Subdomain (e.g., schoolname.platform.com)
    2. User's tenant (if authenticated)
    3. Default tenant (for system admin)
    """

    def process_request(self, request):
        """Extract and set tenant on request object."""
        tenant = None

        # Try to get tenant from subdomain
        host = request.get_host().split(':')[0]  # Remove port
        host_parts = host.split('.')

        if len(host_parts) > 2:
            # subdomain.domain.com format
            subdomain = host_parts[0]
            if subdomain != 'www':
                try:
                    tenant = Tenant.objects.get(slug=subdomain, is_active=True)
                    logger.debug(f"Tenant resolved from subdomain: {tenant.name}")
                except Tenant.DoesNotExist:
                    logger.warning(f"Tenant not found for subdomain: {subdomain}")

        # Fallback: Get tenant from authenticated user
        if not tenant and request.user.is_authenticated:
            if hasattr(request.user, 'tenant') and request.user.tenant:
                tenant = request.user.tenant
                logger.debug(f"Tenant resolved from user: {tenant.name}")

        # Set tenant on request (can be None for system admin or public pages)
        request.tenant = tenant
        logger.debug(f"Request tenant set to: {tenant.name if tenant else 'None'}")

    def process_response(self, request, response):
        """Cleanup if needed."""
        return response
