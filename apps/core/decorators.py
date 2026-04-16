"""
Reusable decorators for views and functions.
"""

import logging
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from apps.core.utils.response import APIResponse

logger = logging.getLogger(__name__)


def role_required(allowed_roles):
    """
    Decorator to restrict view access based on user roles.

    Usage:
        @role_required(['teacher', 'admin'])
        def my_view(request):
            ...

    Args:
        allowed_roles: List of role names that can access the view
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.error(request, "Please log in to access this page.")
                return redirect('auth:login')

            user_role = request.user.role.name if hasattr(request.user, 'role') and request.user.role else None

            if user_role not in allowed_roles:
                logger.warning(
                    f"Access denied for user {request.user.email} with role {user_role} "
                    f"to view requiring roles: {allowed_roles}"
                )
                # Check if this is an API request
                if request.path.startswith('/api/') or request.headers.get('Accept') == 'application/json':
                    return APIResponse.forbidden("You don't have permission to access this resource.")
                else:
                    messages.error(request, "You don't have permission to access this page.")
                    return redirect('core:dashboard')

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def tenant_required(view_func):
    """
    Decorator to ensure request has a valid tenant.

    Usage:
        @tenant_required
        def my_view(request):
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not hasattr(request, 'tenant') or request.tenant is None:
            logger.warning(f"Tenant required but not found for path: {request.path}")

            if request.path.startswith('/api/') or request.headers.get('Accept') == 'application/json':
                return APIResponse.error("Tenant context required", status=400)
            else:
                messages.error(request, "School/tenant context is required for this action.")
                return redirect('core:dashboard')

        return view_func(request, *args, **kwargs)
    return wrapper


def log_action(action_name):
    """
    Decorator to log user actions.

    Usage:
        @log_action("document_uploaded")
        def upload_document(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            user = request.user if request.user.is_authenticated else None
            tenant = getattr(request, 'tenant', None)

            logger.info(
                f"Action: {action_name}",
                extra={
                    'user': user.email if user else 'Anonymous',
                    'tenant': tenant.name if tenant else None,
                    'path': request.path,
                    'method': request.method,
                }
            )

            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def ajax_required(view_func):
    """
    Decorator to ensure request is an AJAX/API request.

    Usage:
        @ajax_required
        def my_api_view(request):
            ...
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        is_ajax = (
            request.headers.get('X-Requested-With') == 'XMLHttpRequest' or
            request.headers.get('Accept') == 'application/json' or
            request.path.startswith('/api/')
        )

        if not is_ajax:
            return APIResponse.error("This endpoint only accepts AJAX requests", status=400)

        return view_func(request, *args, **kwargs)
    return wrapper
