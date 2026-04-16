"""
Management command to create a System Administrator user.
System Admins have access to manage tenants and users but NOT Django Admin.
"""

from django.core.management.base import BaseCommand
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from apps.accounts.models import User, Role


class Command(BaseCommand):
    help = 'Create a System Administrator user (without Django Admin access)'

    def add_arguments(self, parser):
        parser.add_argument('--email', type=str, help='Email address for the system admin')
        parser.add_argument('--first-name', type=str, help='First name')
        parser.add_argument('--last-name', type=str, help='Last name')
        parser.add_argument('--password', type=str, help='Password (will prompt if not provided)')

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n🔧 Create System Administrator\n'))
        self.stdout.write('=' * 50)

        # Get System Admin role
        try:
            system_admin_role = Role.objects.get(name='system_admin')
        except Role.DoesNotExist:
            self.stdout.write(self.style.ERROR('\n❌ System Admin role not found!'))
            self.stdout.write('Please run: python manage.py create_roles')
            return

        # Get email
        email = options.get('email')
        if not email:
            email = input('\nEmail address: ').strip()

        # Validate email
        try:
            validate_email(email)
        except ValidationError:
            self.stdout.write(self.style.ERROR(f'\n❌ Invalid email address: {email}'))
            return

        # Check if user already exists
        if User.objects.filter(email=email).exists():
            self.stdout.write(self.style.ERROR(f'\n❌ User with email {email} already exists!'))
            return

        # Get first name
        first_name = options.get('first_name')
        if not first_name:
            first_name = input('First name: ').strip()

        # Get last name
        last_name = options.get('last_name')
        if not last_name:
            last_name = input('Last name: ').strip()

        # Get password
        password = options.get('password')
        if not password:
            from getpass import getpass
            password = getpass('Password: ')
            password_confirm = getpass('Password (again): ')

            if password != password_confirm:
                self.stdout.write(self.style.ERROR('\n❌ Passwords do not match!'))
                return

        # Validate password
        if len(password) < 8:
            self.stdout.write(self.style.ERROR('\n❌ Password must be at least 8 characters long!'))
            return

        # Create user
        try:
            user = User.objects.create_user(
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name,
                role=system_admin_role,
                is_active=True,
                is_staff=False,  # No Django Admin access
                is_superuser=False,  # Not a superuser
                tenant=None  # System admins don't belong to a specific tenant
            )

            self.stdout.write(self.style.SUCCESS('\n✅ System Administrator created successfully!\n'))
            self.stdout.write('=' * 50)
            self.stdout.write(f'\nEmail: {user.email}')
            self.stdout.write(f'Name: {user.get_full_name()}')
            self.stdout.write(f'Role: {user.role.display_name}')
            self.stdout.write(f'Django Admin Access: ❌ No')
            self.stdout.write(f'System Admin Dashboard: ✅ Yes')
            self.stdout.write('\n' + '=' * 50)
            self.stdout.write(self.style.SUCCESS('\n🎉 User can now login at: /auth/login/\n'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Error creating user: {str(e)}'))
