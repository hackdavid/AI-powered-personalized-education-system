# EduAI Platform - Quick Start Guide

## Setup Instructions

### 1. Install Dependencies

```bash
# Navigate to project directory
cd eduai_platform

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install requirements
pip install -r requirements/development.txt
```

### 2. Environment Configuration

```bash
# Copy environment template
cp .env.example .env

# Edit .env and add your API keys (optional for basic setup)
# Minimum required: DJANGO_SECRET_KEY
```

### 3. Database Setup

```bash
# Run migrations
python manage.py migrate

# Create default roles and permissions
python manage.py create_roles

# Create superuser
python manage.py createsuperuser
```

### 4. Run Development Server

```bash
python manage.py runserver
```

Visit: http://127.0.0.1:8000/

## Initial Setup Steps

### 1. Access Django Admin

- Go to: http://127.0.0.1:8000/admin/
- Login with superuser credentials

### 2. Create a Tenant (School)

In Django Admin:
1. Go to **Tenants** → **Add Tenant**
2. Fill in:
   - Name: "Test School"
   - Slug: "testschool"
   - Is Active: ✓
3. Save

### 3. Create Test Users

For each role, create a user:

**Student:**
- Email: student@test.com
- Role: Student
- Tenant: Test School
- Grade Level: 8

**Teacher:**
- Email: teacher@test.com
- Role: Teacher
- Tenant: Test School

**School Admin:**
- Email: admin@test.com
- Role: School Administrator
- Tenant: Test School

### 4. Create Classes and Subjects

**Subject Example:**
- Tenant: Test School
- Name: Mathematics
- Code: MATH
- Is Active: ✓

**Class Example:**
- Tenant: Test School
- Name: Grade 8 - Section A
- Grade Level: 8
- Section: A
- Academic Year: 2024-2025
- Is Active: ✓

## Testing the System

### 1. Test Role-Based Dashboards

Logout from admin and login as:

- **Student**: See student dashboard with assignments and progress
- **Teacher**: See teacher dashboard with class management
- **School Admin**: See admin dashboard with school management

### 2. Test Frontend Utilities

Open browser console and try:

```javascript
// Test Toast
Toast.success('Hello World!');
Toast.error('This is an error');

// Test API Client
const result = await APIClient.get('/health/');
console.log(result);

// Test Modal
const confirmed = await Modal.confirm({
    title: 'Test Modal',
    message: 'This is a test'
});
console.log('Confirmed:', confirmed);
```

## Project Structure Overview

```
eduai_platform/
├── apps/
│   ├── core/          - Infrastructure (middleware, utils, decorators)
│   ├── accounts/      - Authentication and RBAC
│   ├── tenants/       - Multi-tenant management
│   └── common/        - Shared models (Subject, Class)
│
├── frontend/
│   ├── static/js/core/    - JavaScript utilities
│   ├── static/css/        - Core CSS
│   └── templates/         - HTML templates
│
└── config/
    └── settings/          - Django settings
```

## Next Steps

### Phase 2: Implement Feature Apps

1. **Ingestion App** - Document upload and processing
2. **Tutoring App** - AI-powered tutoring with RAG
3. **Assessments App** - Assignment creation and grading
4. **Analytics App** - Student progress tracking
5. **Goals App** - Gamified learning goals

### Development Workflow

1. Create new app in `apps/` directory
2. Use base models from `apps.core.models.base`
3. Use `APIResponse` for all API endpoints
4. Protect views with `@role_required` decorator
5. Use frontend utilities for UI

### Example: Creating a New View

```python
from django.shortcuts import render
from apps.core.decorators import role_required
from apps.core.utils.response import APIResponse

@role_required(['teacher'])
def create_assignment(request):
    if request.method == 'POST':
        # Process form
        return APIResponse.success(
            data={'assignment_id': 123},
            message='Assignment created successfully'
        )
    return render(request, 'assignments/create.html')
```

### Example: Frontend Form

```html
<form id="assignment-form" action="/api/assignments/" method="POST">
    {% csrf_token %}
    <input type="text" name="title" required>
    <button type="submit">Create</button>
</form>

<script>
FormHandler.initialize(document.getElementById('assignment-form'), {
    onSuccess: (result) => {
        Toast.success('Assignment created!');
        window.location.href = '/teacher/assignments/';
    }
});
</script>
```

## Common Commands

```bash
# Run tests
python manage.py test

# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Collect static files (for production)
python manage.py collectstatic

# Run development server
python manage.py runserver

# Access Python shell with Django context
python manage.py shell
```

## Troubleshooting

### Issue: ModuleNotFoundError

```bash
# Ensure virtual environment is activated
# Reinstall requirements
pip install -r requirements/development.txt
```

### Issue: Database locked (SQLite)

```bash
# Stop all running servers
# Delete db.sqlite3
# Run migrations again
python manage.py migrate
```

### Issue: Static files not loading

```bash
# Collect static files
python manage.py collectstatic --noinput
```

## Support

- Check `README.md` for detailed documentation
- Review `IMPLEMENTATION_PLAN.md` for architecture details
- See code comments for inline documentation

---

**Happy Coding! 🚀**
