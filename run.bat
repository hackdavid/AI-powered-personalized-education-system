@echo off
echo ========================================
echo Starting EduAI Platform
echo ========================================
echo.

REM Check if virtual environment exists
if not exist "venv\" (
    echo [✗] Virtual environment not found!
    echo [!] Please run setup.bat first
    pause
    exit /b 1
)

echo [*] Activating virtual environment...
call venv\Scripts\activate.bat

echo [*] Starting development server...
echo.
echo ========================================
echo Server will be available at:
echo http://127.0.0.1:8000/
echo ========================================
echo.
echo Press Ctrl+C to stop the server
echo.

python manage.py runserver
