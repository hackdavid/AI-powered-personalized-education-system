@echo off
echo ========================================
echo Exporting Test Data to Fixtures
echo ========================================
echo.

REM Create fixtures directory if it doesn't exist
if not exist "fixtures" mkdir fixtures

echo [*] Exporting roles and permissions...
python manage.py dumpdata accounts.Role accounts.Permission --indent 2 --output fixtures/roles_permissions.json

echo [*] Exporting tenants...
python manage.py dumpdata tenants.Tenant --indent 2 --output fixtures/tenants.json

echo [*] Exporting users...
python manage.py dumpdata accounts.User --indent 2 --output fixtures/users.json

echo [*] Exporting subjects and classes...
python manage.py dumpdata common.Subject common.Class common.ClassSubject --indent 2 --output fixtures/academic.json

echo.
echo ========================================
echo [SUCCESS] Fixtures exported!
echo ========================================
echo.
echo Fixtures saved in ./fixtures/ directory:
echo - roles_permissions.json
echo - tenants.json
echo - users.json
echo - academic.json
echo.
echo These can be committed to Git!
echo ========================================
pause
