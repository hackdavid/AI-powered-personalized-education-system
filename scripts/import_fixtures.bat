@echo off
echo ========================================
echo Importing Test Data from Fixtures
echo ========================================
echo.

REM Check if fixtures directory exists
if not exist "fixtures" (
    echo [ERROR] fixtures directory not found!
    echo Please run export_fixtures.bat first.
    pause
    exit /b 1
)

echo [*] Importing roles and permissions...
python manage.py loaddata fixtures/roles_permissions.json

echo [*] Importing tenants...
python manage.py loaddata fixtures/tenants.json

echo [*] Importing users...
python manage.py loaddata fixtures/users.json

echo [*] Importing subjects and classes...
python manage.py loaddata fixtures/academic.json

echo.
echo ========================================
echo [SUCCESS] Test data imported!
echo ========================================
echo.
echo You can now:
echo 1. Login with test users
echo 2. Start developing
echo.
echo Test accounts:
echo - admin@test.com (Superuser)
echo - sysadmin@test.com (System Admin)
echo - schooladmin@test.com (School Admin)
echo - teacher@test.com (Teacher)
echo - student@test.com (Student)
echo.
echo Default password: testpass123
echo ========================================
pause
