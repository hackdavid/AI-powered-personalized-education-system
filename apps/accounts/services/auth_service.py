"""
Authentication service for user login, logout, and password management.
"""

import logging
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from apps.accounts.models import User

logger = logging.getLogger(__name__)


class AuthService:
    """Service class for authentication operations."""

    @staticmethod
    def login_user(request, email, password, remember_me=False):
        """
        Authenticate and log in a user.

        Args:
            request: HTTP request object
            email: User email
            password: User password
            remember_me: Whether to persist session

        Returns:
            tuple: (success: bool, user: User or None, message: str)
        """
        try:
            # Authenticate user
            user = authenticate(request, username=email, password=password)

            if user is None:
                logger.warning(f"Failed login attempt for email: {email}")
                return False, None, "Invalid email or password"

            if not user.is_active:
                logger.warning(f"Inactive user login attempt: {email}")
                return False, None, "Your account has been deactivated. Please contact support."

            if user.tenant and not user.tenant.is_active:
                logger.warning(f"Login attempt for inactive tenant: {user.tenant.name}")
                return False, None, "Your school's account is inactive. Please contact your administrator."

            # Log in the user
            login(request, user)

            # Set session expiry
            if not remember_me:
                request.session.set_expiry(0)  # Session expires when browser closes
            else:
                request.session.set_expiry(1209600)  # 2 weeks

            # Update last login IP
            user.last_login_ip = AuthService._get_client_ip(request)
            user.save(update_fields=['last_login', 'last_login_ip'])

            logger.info(f"User logged in successfully: {email}")
            return True, user, "Login successful"

        except Exception as e:
            logger.error(f"Login error for {email}: {str(e)}", exc_info=True)
            return False, None, "An error occurred during login. Please try again."

    @staticmethod
    def logout_user(request):
        """
        Log out the current user.

        Args:
            request: HTTP request object

        Returns:
            bool: True if logout successful
        """
        try:
            email = request.user.email if request.user.is_authenticated else 'Unknown'
            logout(request)
            logger.info(f"User logged out: {email}")
            return True
        except Exception as e:
            logger.error(f"Logout error: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def change_password(user, old_password, new_password):
        """
        Change user password.

        Args:
            user: User object
            old_password: Current password
            new_password: New password

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            # Verify old password
            if not user.check_password(old_password):
                return False, "Current password is incorrect"

            # Set new password
            user.set_password(new_password)
            user.save()

            logger.info(f"Password changed for user: {user.email}")
            return True, "Password changed successfully"

        except Exception as e:
            logger.error(f"Password change error for {user.email}: {str(e)}", exc_info=True)
            return False, "An error occurred while changing password"

    @staticmethod
    def initiate_password_reset(email):
        """
        Initiate password reset process.

        Args:
            email: User email

        Returns:
            tuple: (success: bool, token: str or None, uid: str or None, message: str)
        """
        try:
            user = User.objects.get(email=email, is_active=True)

            # Generate password reset token
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))

            logger.info(f"Password reset initiated for: {email}")
            return True, token, uid, "Password reset email sent"

        except User.DoesNotExist:
            # Don't reveal if user exists for security
            logger.warning(f"Password reset attempted for non-existent email: {email}")
            return True, None, None, "Password reset email sent"

        except Exception as e:
            logger.error(f"Password reset error: {str(e)}", exc_info=True)
            return False, None, None, "An error occurred. Please try again."

    @staticmethod
    def verify_email(user):
        """
        Mark user email as verified.

        Args:
            user: User object

        Returns:
            bool: True if successful
        """
        try:
            user.is_verified = True
            user.save(update_fields=['is_verified'])
            logger.info(f"Email verified for user: {user.email}")
            return True
        except Exception as e:
            logger.error(f"Email verification error: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def _get_client_ip(request):
        """Extract client IP address from request."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
