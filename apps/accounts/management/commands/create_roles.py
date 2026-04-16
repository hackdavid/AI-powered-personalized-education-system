"""
Management command to create default roles and permissions.
"""

from django.core.management.base import BaseCommand
from apps.accounts.models import Role, Permission


class Command(BaseCommand):
    help = 'Create default roles and permissions for the system'

    def handle(self, *args, **kwargs):
        self.stdout.write('Creating default roles and permissions...')

        # Create default permissions
        permissions_data = [
            # Student permissions
            {'code': 'view_assignments', 'name': 'View Assignments', 'category': 'assignments'},
            {'code': 'submit_assignments', 'name': 'Submit Assignments', 'category': 'assignments'},
            {'code': 'use_ai_tutor', 'name': 'Use AI Tutor', 'category': 'tutoring'},
            {'code': 'view_own_progress', 'name': 'View Own Progress', 'category': 'analytics'},
            {'code': 'manage_own_goals', 'name': 'Manage Own Goals', 'category': 'goals'},

            # Teacher permissions
            {'code': 'create_assignments', 'name': 'Create Assignments', 'category': 'assignments'},
            {'code': 'grade_assignments', 'name': 'Grade Assignments', 'category': 'assignments'},
            {'code': 'view_student_progress', 'name': 'View Student Progress', 'category': 'analytics'},
            {'code': 'generate_questions', 'name': 'Generate Questions with AI', 'category': 'assignments'},
            {'code': 'view_analytics', 'name': 'View Analytics', 'category': 'analytics'},

            # School Admin permissions
            {'code': 'manage_users', 'name': 'Manage Users', 'category': 'administration'},
            {'code': 'manage_classes', 'name': 'Manage Classes', 'category': 'administration'},
            {'code': 'manage_subjects', 'name': 'Manage Subjects', 'category': 'administration'},
            {'code': 'upload_documents', 'name': 'Upload Documents', 'category': 'documents'},
            {'code': 'view_school_analytics', 'name': 'View School Analytics', 'category': 'analytics'},
            {'code': 'manage_school_settings', 'name': 'Manage School Settings', 'category': 'administration'},

            # System Admin permissions
            {'code': 'manage_tenants', 'name': 'Manage Tenants', 'category': 'system'},
            {'code': 'manage_all_users', 'name': 'Manage All Users', 'category': 'system'},
            {'code': 'view_system_logs', 'name': 'View System Logs', 'category': 'system'},
            {'code': 'system_configuration', 'name': 'System Configuration', 'category': 'system'},
        ]

        created_permissions = {}
        for perm_data in permissions_data:
            permission, created = Permission.objects.get_or_create(
                code=perm_data['code'],
                defaults={
                    'name': perm_data['name'],
                    'category': perm_data['category']
                }
            )
            created_permissions[perm_data['code']] = permission
            if created:
                self.stdout.write(self.style.SUCCESS(f'  [+] Created permission: {permission.name}'))
            else:
                self.stdout.write(f'  [-] Permission already exists: {permission.name}')

        # Create default roles
        roles_data = [
            {
                'name': Role.STUDENT,
                'display_name': 'Student',
                'description': 'Students can view assignments, use AI tutor, and track their progress',
                'level': 30,
                'permissions': [
                    'view_assignments',
                    'submit_assignments',
                    'use_ai_tutor',
                    'view_own_progress',
                    'manage_own_goals'
                ]
            },
            {
                'name': Role.TEACHER,
                'display_name': 'Teacher',
                'description': 'Teachers can create assignments, grade submissions, and view student analytics',
                'level': 20,
                'permissions': [
                    'view_assignments',
                    'create_assignments',
                    'grade_assignments',
                    'generate_questions',
                    'view_student_progress',
                    'view_analytics'
                ]
            },
            {
                'name': Role.SCHOOL_ADMIN,
                'display_name': 'School Administrator',
                'description': 'School admins can manage users, classes, subjects, and school settings',
                'level': 10,
                'permissions': [
                    'manage_users',
                    'manage_classes',
                    'manage_subjects',
                    'upload_documents',
                    'view_school_analytics',
                    'manage_school_settings',
                    'create_assignments',
                    'grade_assignments',
                    'view_student_progress',
                    'view_analytics'
                ]
            },
            {
                'name': Role.SYSTEM_ADMIN,
                'display_name': 'System Administrator',
                'description': 'System admins have full access to all system features',
                'level': 1,
                'permissions': list(created_permissions.keys())  # All permissions
            }
        ]

        for role_data in roles_data:
            role, created = Role.objects.get_or_create(
                name=role_data['name'],
                defaults={
                    'display_name': role_data['display_name'],
                    'description': role_data['description'],
                    'level': role_data['level']
                }
            )

            if created:
                self.stdout.write(self.style.SUCCESS(f'[+] Created role: {role.display_name}'))
            else:
                self.stdout.write(f'[-] Role already exists: {role.display_name}')

            # Assign permissions
            permission_objects = [created_permissions[code] for code in role_data['permissions'] if code in created_permissions]
            role.permissions.set(permission_objects)
            self.stdout.write(f'  Assigned {len(permission_objects)} permissions')

        self.stdout.write(self.style.SUCCESS('\n[SUCCESS] All roles and permissions created/updated!'))
