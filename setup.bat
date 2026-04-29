@echo off
echo ========================================
echo EduAI Platform - Quick Setup Script
echo ========================================
echo.

REM Check if virtual environment exists
if exist "venv\" (
    echo [✓] Virtual environment already exists
) else (
    echo [*] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [✗] Failed to create virtual environment
        pause
        exit /b 1
    )
    echo [✓] Virtual environment created
)

echo.
echo [*] Activating virtual environment...
call venv\Scripts\activate.bat

echo.
echo [*] Installing dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo [✗] Failed to install dependencies
    pause
    exit /b 1
)
echo [✓] Dependencies installed

echo.
REM Check if .env exists
if exist ".env" (
    echo [✓] .env file already exists
) else (
    echo [*] Creating .env file from template...
    copy .env.example .env
    echo [✓] .env file created
    echo [!] Please update .env with your configuration
)

echo.
REM Check if database exists
if exist "db.sqlite3" (
    echo [✓] Database already exists
) else (
    echo [*] Running database migrations...
    python manage.py migrate
    if errorlevel 1 (
        echo [✗] Failed to run migrations
        pause
        exit /b 1
    )
    echo [✓] Database migrations complete
)

echo.
echo [*] Creating default roles and permissions...
python manage.py create_roles
if errorlevel 1 (
    echo [✗] Failed to create roles
    pause
    exit /b 1
)
echo [✓] Roles created

echo.
echo ========================================
echo Setup Complete! 🎉
echo ========================================
echo.
echo Next steps:
echo 1. Create superuser: python manage.py createsuperuser
echo 2. Run server: python manage.py runserver
echo 3. Visit: http://127.0.0.1:8000/
echo.
echo See SETUP_AND_TEST.md for detailed instructions
echo ========================================
echo.
pause
