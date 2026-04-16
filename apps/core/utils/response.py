"""
Standardized API Response Utilities
"""

from django.http import JsonResponse
from django.utils import timezone
from typing import Any, Dict, Optional


class APIResponse:
    """
    Standardized API response format for consistent client-side handling.

    All API responses follow this structure:
    {
        "success": bool,
        "message": str,
        "data": any,
        "errors": dict (optional),
        "timestamp": str (ISO format)
    }
    """

    @staticmethod
    def success(
        data: Any = None,
        message: str = "",
        status: int = 200,
        **kwargs
    ) -> JsonResponse:
        """
        Return a successful API response.

        Args:
            data: Response payload
            message: Success message
            status: HTTP status code (default: 200)
            **kwargs: Additional fields to include in response

        Returns:
            JsonResponse with success=True
        """
        response_data = {
            "success": True,
            "message": message,
            "data": data,
            "timestamp": timezone.now().isoformat()
        }
        response_data.update(kwargs)
        return JsonResponse(response_data, status=status)

    @staticmethod
    def error(
        message: str,
        errors: Optional[Dict] = None,
        status: int = 400,
        **kwargs
    ) -> JsonResponse:
        """
        Return an error API response.

        Args:
            message: Error message
            errors: Dictionary of field-specific errors
            status: HTTP status code (default: 400)
            **kwargs: Additional fields to include in response

        Returns:
            JsonResponse with success=False
        """
        response_data = {
            "success": False,
            "message": message,
            "errors": errors or {},
            "timestamp": timezone.now().isoformat()
        }
        response_data.update(kwargs)
        return JsonResponse(response_data, status=status)

    @staticmethod
    def not_found(message: str = "Resource not found") -> JsonResponse:
        """Return a 404 not found response."""
        return APIResponse.error(message, status=404)

    @staticmethod
    def forbidden(message: str = "You don't have permission to access this resource") -> JsonResponse:
        """Return a 403 forbidden response."""
        return APIResponse.error(message, status=403)

    @staticmethod
    def unauthorized(message: str = "Authentication required") -> JsonResponse:
        """Return a 401 unauthorized response."""
        return APIResponse.error(message, status=401)

    @staticmethod
    def validation_error(errors: Dict, message: str = "Validation failed") -> JsonResponse:
        """Return a 400 validation error response."""
        return APIResponse.error(message, errors=errors, status=400)

    @staticmethod
    def server_error(message: str = "An internal server error occurred") -> JsonResponse:
        """Return a 500 server error response."""
        return APIResponse.error(message, status=500)
