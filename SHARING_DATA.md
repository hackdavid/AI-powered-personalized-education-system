# Sharing Development Data with Team

## ❌ Don't Upload SQLite Database

**Never commit `db.sqlite3` to Git!** It causes:
- Merge conflicts
- Security issues
- Large repo size
- Can't track changes

## ✅ Use Django Fixtures Instead

Fixtures are JSON/YAML exports of your data that can be safely committed to Git.

---

## For Original Developer (You)

### Step 1: Create Test Data
```bash
# 1. Create superuser
python manage.py createsuperuser

# 2. Create roles
python manage.py create_roles

# 3. In Django Admin, create:
#    - Tenant (Test School)
#    - Users (student, teacher, admin)
#    - Subjects (Math, English, Science)
#    - Classes (Grade 8-A, Grade 9-B)
```

### Step 2: Export to Fixtures
```bash
# Run the export script
scripts\export_fixtures.bat

# Or manually:
python manage.py dumpdata accounts.Role accounts.Permission --indent 2 > fixtures/roles_permissions.json
python manage.py dumpdata tenants.Tenant --indent 2 > fixtures/tenants.json
python manage.py dumpdata accounts.User --indent 2 > fixtures/users.json
python manage.py dumpdata common.Subject common.Class --indent 2 > fixtures/academic.json
```

### Step 3: Update .gitignore
Make sure your `.gitignore` has:
```
# Database
*.sqlite3
*.db

# But allow fixtures
!fixtures/*.json
```

### Step 4: Commit Fixtures
```bash
git add fixtures/
git add scripts/export_fixtures.bat
git add scripts/import_fixtures.bat
git commit -m "Add test data fixtures for development"
git push
```

---

## For Other Developers

### Step 1: Clone Repository
```bash
git clone <repository-url>
cd eduai_platform
```

### Step 2: Setup Environment
```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements/development.txt

# Copy environment file
copy .env.example .env
```

### Step 3: Setup Database
```bash
# Create database tables
python manage.py migrate
```

### Step 4: Import Test Data
```bash
# Run the import script
scripts\import_fixtures.bat

# Or manually:
python manage.py loaddata fixtures/roles_permissions.json
python manage.py loaddata fixtures/tenants.json
python manage.py loaddata fixtures/users.json
python manage.py loaddata fixtures/academic.json
```

### Step 5: Start Development
```bash
python manage.py runserver
```

Login with test accounts:
- `admin@test.com` (Superuser)
- `student@test.com` (Student)
- `teacher@test.com` (Teacher)

Default password: `testpass123`

---

## Updating Fixtures

When you add new test data:

```bash
# 1. Add data via Django Admin or app

# 2. Export updated fixtures
scripts\export_fixtures.bat

# 3. Commit changes
git add fixtures/
git commit -m "Update test data fixtures"
git push
```

Other developers can then:
```bash
git pull
python manage.py loaddata fixtures/*.json
```

---

## Alternative: Management Command for Test Data

Even better - create a management command that generates test data programmatically:

**File:** `apps/accounts/management/commands/create_test_data.py`

```python
from django.core.management.base import BaseCommand
from apps.accounts.models import User, Role
from apps.tenants.models import Tenant
from apps.common.models import Subject, Class

class Command(BaseCommand):
    help = 'Create test data for development'

    def handle(self, *args, **kwargs):
        # Create tenant
        tenant, _ = Tenant.objects.get_or_create(
            slug='testschool',
            defaults={
                'name': 'Test School',
                'is_active': True
            }
        )
        
        # Get roles
        student_role = Role.objects.get(name='student')
        teacher_role = Role.objects.get(name='teacher')
        
        # Create users
        student, _ = User.objects.get_or_create(
            email='student@test.com',
            defaults={
                'first_name': 'John',
                'last_name': 'Doe',
                'tenant': tenant,
                'role': student_role,
                'grade_level': 8
            }
        )
        if _:
            student.set_password('testpass123')
            student.save()
        
        # ... create more users, subjects, classes
        
        self.stdout.write(self.style.SUCCESS('Test data created!'))
```

Then developers just run:
```bash
python manage.py create_test_data
```

---

## Comparison

| Method | Pros | Cons | Best For |
|--------|------|------|----------|
| **SQLite File** | ❌ Easy | ❌ Binary, conflicts, security | Nothing |
| **Fixtures** | ✅ Version control, sharable | ⚠️ Manual export | Small datasets |
| **Management Command** | ✅ Automated, consistent | ⚠️ Need to code | Best practice |
| **Factory Boy** | ✅ Flexible, testing | ⚠️ Learning curve | Large teams |

---

## Recommended Approach

1. **For simple projects:** Use fixtures (what we set up above)
2. **For complex projects:** Create management command
3. **For testing:** Use Factory Boy or pytest fixtures
4. **Never:** Commit SQLite database

---

## Security Notes

### Don't Export Sensitive Data
```bash
# Exclude users with real data
python manage.py dumpdata accounts.User --exclude auth.Permission --natural-foreign --natural-primary > fixtures/users.json
```

### Reset Passwords After Import
```python
# In create_test_data.py
for user in User.objects.all():
    user.set_password('testpass123')
    user.save()
```

### Use Secure Passwords in Production
Never use `testpass123` in production!

---

## Quick Reference

### Export All Data
```bash
python manage.py dumpdata --exclude auth.permission --exclude contenttypes --exclude sessions --indent 2 > fixtures/all_data.json
```

### Import All Data
```bash
python manage.py loaddata fixtures/all_data.json
```

### Export Specific App
```bash
python manage.py dumpdata accounts --indent 2 > fixtures/accounts.json
```

### Reset Database and Import
```bash
rm db.sqlite3
python manage.py migrate
python manage.py loaddata fixtures/*.json
```

---

## Summary

✅ **DO:**
- Export data to fixtures (JSON files)
- Commit fixtures to Git
- Create management commands for test data
- Document test account credentials
- Update fixtures when data changes

❌ **DON'T:**
- Commit SQLite database files
- Include production data in fixtures
- Use real passwords in test data
- Export sensitive information

---

**Result:** Other developers can get the same test data by running one command! 🎉
