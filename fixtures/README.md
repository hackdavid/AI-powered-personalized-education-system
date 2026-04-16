# Test Data Fixtures

This directory contains Django fixtures for development and testing.

## What are Fixtures?

Fixtures are exports of database data in JSON format that can be:
- ✅ Committed to Git (unlike SQLite databases)
- ✅ Shared with team members
- ✅ Version controlled
- ✅ Used for testing

## Files

- `roles_permissions.json` - User roles and permissions
- `tenants.json` - Test schools/organizations
- `users.json` - Test user accounts
- `academic.json` - Subjects, classes, and class-subject assignments

## Usage

### For New Developers

After cloning the repository and running migrations:

```bash
# Import all test data
python manage.py loaddata fixtures/roles_permissions.json
python manage.py loaddata fixtures/tenants.json
python manage.py loaddata fixtures/users.json
python manage.py loaddata fixtures/academic.json

# Or use the script (Windows)
scripts\import_fixtures.bat

# Or use the script (Mac/Linux)
./scripts/import_fixtures.sh
```

### For Creating/Updating Fixtures

After adding or modifying test data:

```bash
# Export updated data
python manage.py dumpdata accounts.Role accounts.Permission --indent 2 > fixtures/roles_permissions.json
python manage.py dumpdata tenants.Tenant --indent 2 > fixtures/tenants.json
python manage.py dumpdata accounts.User --indent 2 > fixtures/users.json
python manage.py dumpdata common.Subject common.Class common.ClassSubject --indent 2 > fixtures/academic.json

# Or use the script (Windows)
scripts\export_fixtures.bat

# Or use the script (Mac/Linux)
./scripts/export_fixtures.sh
```

## Test Accounts

After importing fixtures, you can login with:

| Email | Password | Role |
|-------|----------|------|
| admin@test.com | testpass123 | Django Superuser |
| sysadmin@test.com | testpass123 | System Admin |
| schooladmin@test.com | testpass123 | School Admin |
| teacher@test.com | testpass123 | Teacher |
| student@test.com | testpass123 | Student |

## Important Notes

⚠️ **Security:**
- Never include production data in fixtures
- Never use real passwords
- Don't commit sensitive information

✅ **Best Practices:**
- Keep fixtures small and focused
- Update fixtures when schema changes
- Document test account credentials
- Use consistent test passwords

## Troubleshooting

### "IntegrityError: UNIQUE constraint failed"
The data already exists. Either:
1. Delete `db.sqlite3` and run migrations again
2. Or skip importing that fixture

### "DoesNotExist: Role matching query does not exist"
Import fixtures in this order:
1. roles_permissions.json (first)
2. tenants.json
3. users.json (needs roles and tenants)
4. academic.json (needs tenants)

### "No fixtures found"
Make sure you're in the project root directory where `manage.py` is located.

## Alternative: Management Command

Instead of fixtures, you can create a management command:

```bash
python manage.py create_test_data
```

See `SHARING_DATA.md` for more information.
