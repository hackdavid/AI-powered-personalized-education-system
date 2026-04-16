"""
Role-Based Access Control (RBAC) service for permission checking and management.
"""

import logging
from django.db.models import Q
from apps.accounts.models import Role, Permission

logger = logging.getLogger(__name__)


class RBACService:
    """Service class for role-based access control operations."""

    @staticmethod
    def user_has_permission(user, permission_code):
        """
        Check if a user has a specific permission.

        Args:
            user: User object
            permission_code: Permission code to check

        Returns:
            bool: True if user has permission
        """
        if not user or not user.is_authenticated:
            return False

        # Django superusers have all permissions (technical admin)
        if user.is_superuser:
            return True

        # Check role permissions
        if not user.role:
            return False

        return user.role.has_permission(permission_code)

    @staticmethod
    def user_has_any_permission(user, permission_codes):
        """
        Check if user has any of the specified permissions.

        Args:
            user: User object
            permission_codes: List of permission codes

        Returns:
            bool: True if user has at least one permission
        """
        if not user or not user.is_authenticated:
            return False

        if user.is_superuser:
            return True

        if not user.role:
            return False

        return any(user.role.has_permission(code) for code in permission_codes)

    @staticmethod
    def user_has_all_permissions(user, permission_codes):
        """
        Check if user has all of the specified permissions.

        Args:
            user: User object
            permission_codes: List of permission codes

        Returns:
            bool: True if user has all permissions
        """
        if not user or not user.is_authenticated:
            return False

        if user.is_superuser:
            return True

        if not user.role:
            return False

        return all(user.role.has_permission(code) for code in permission_codes)

    @staticmethod
    def filter_by_role_access(queryset, user, tenant_field='tenant'):
        """
        Filter queryset based on user's role and tenant.

        Args:
            queryset: Django queryset to filter
            user: User object
            tenant_field: Field name for tenant relation (default: 'tenant')

        Returns:
            Filtered queryset
        """
        if not user or not user.is_authenticated:
            return queryset.none()

        # System admins see everything
        if user.is_system_admin:
            return queryset

        # Other roles see only their tenant's data
        if user.tenant:
            filter_kwargs = {tenant_field: user.tenant}
            return queryset.filter(**filter_kwargs)

        return queryset.none()

    @staticmethod
    def get_user_permissions(user):
        """
        Get all permissions for a user.

        Args:
            user: User object

        Returns:
            QuerySet of Permission objects
        """
        if not user or not user.is_authenticated or not user.role:
            return Permission.objects.none()

        if user.is_superuser:
            return Permission.objects.all()

        return user.role.permissions.all()

    @staticmethod
    def can_access_tenant(user, tenant):
        """
        Check if user can access a specific tenant.

        Args:
            user: User object
            tenant: Tenant object

        Returns:
            bool: True if user can access tenant
        """
        if not user or not user.is_authenticated:
            return False

        # System admins can access all tenants
        if user.is_system_admin:
            return True

        # Users can only access their own tenant
        return user.tenant == tenant

    @staticmethod
    def can_manage_user(acting_user, target_user):
        """
        Check if acting_user can manage target_user.

        Args:
            acting_user: User performing the action
            target_user: User being managed

        Returns:
            bool: True if acting_user can manage target_user
        """
        if not acting_user or not acting_user.is_authenticated:
            return False

        # System admins can manage all users
        if acting_user.is_system_admin:
            return True

        # School admins can manage users in their tenant
        if acting_user.is_school_admin:
            return target_user.tenant == acting_user.tenant

        # Teachers can manage students in their classes (to be implemented with class relations)
        if acting_user.is_teacher and target_user.is_student:
            return target_user.tenant == acting_user.tenant

        return False

    @staticmethod
    def get_accessible_users(user):
        """
        Get all users that the given user can access.

        Args:
            user: User object

        Returns:
            QuerySet of User objects
        """
        from apps.accounts.models import User

        if not user or not user.is_authenticated:
            return User.objects.none()

        # System admins can access all users
        if user.is_system_admin:
            return User.objects.all()

        # School admins can access users in their tenant
        if user.is_school_admin and user.tenant:
            return User.objects.filter(tenant=user.tenant)

        # Teachers can access students in their tenant
        if user.is_teacher and user.tenant:
            return User.objects.filter(tenant=user.tenant, role__name='student')

        # Students can only access themselves
        return User.objects.filter(id=user.id)

    @staticmethod
    def initialize_default_roles():
        """
        Initialize default roles and permissions.
        Call this in a management command or migration.
        """
        # Define default roles
        default_roles = [
            {
                'name': Role.SYSTEM_ADMIN,
                'display_name': 'System Administrator',
                'description': 'Full system access, manages all tenants',
                'level': 1
            },
            {
                'name': Role.SCHOOL_ADMIN,
                'display_name': 'School Administrator',
                'description': 'Manages school settings, users, and content',
                'level': 10
            },
            {
                'name': Role.TEACHER,
                'display_name': 'Teacher',
                'description': 'Creates assignments, views student progress',
                'level': 20
            },
            {
                'name': Role.STUDENT,
                'display_name': 'Student',
                'description': 'Accesses learning materials and assignments',
                'level': 30
            },
        ]

        for role_data in default_roles:
            role, created = Role.objects.get_or_create(
                name=role_data['name'],
                defaults=role_data
            )
            if created:
                logger.info(f"Created default role: {role.name}")

        logger.info("Default roles initialized")
