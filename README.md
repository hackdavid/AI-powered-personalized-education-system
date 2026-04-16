# EduAI Platform - AI-Powered Personalized Education System

A production-ready Django-based platform for personalized education with AI tutoring, RAG-based content grounding, and role-based access control.

## Features

- 🔐 **Multi-tenant Architecture** - Complete data isolation per school
- 👥 **Role-Based Access Control** - Student, Teacher, School Admin, System Admin
- 🤖 **AI-Powered Tutoring** - RAG-based tutoring with curriculum grounding
- 📚 **Document Ingestion** - PDF/DOCX processing pipeline
- 📊 **Analytics Dashboard** - Student progress tracking and heatmaps
- 🎯 **Gamified Learning** - Goal-based progression system
- 📝 **Assignment Management** - AI-powered question generation

## Architecture

This project follows a modular architecture with:

- **Core Infrastructure** - Centralized middleware, decorators, and utilities
- **Accounts System** - Custom user model with RBAC
- **Multi-tenancy** - Tenant-aware models and middleware
- **Frontend Utilities** - Reusable JavaScript components
- **Service Layer** - Business logic separated from views

## Tech Stack

- **Backend**: Django 4.2
- **Database**: PostgreSQL (SQLite for development)
- **AI/ML**: OpenAI API, Anthropic Claude, LangChain
- **Vector Store**: ChromaDB
- **Task Queue**: Celery + Redis (for production)
- **Frontend**: Vanilla JavaScript with utility modules

## Getting Started

### Prerequisites

- Python 3.9+
- PostgreSQL (optional for development)
- Redis (optional, for Celery in production)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd eduai_platform
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements/development.txt
   ```

4. **Setup environment variables**
   ```bash
   cp .env.example .env
   # Edit .env and add your API keys
   ```

5. **Run migrations**
   ```bash
   python manage.py migrate
   ```

6. **Create initial data**
   ```bash
   python manage.py create_roles  # Creates default roles
   python manage.py createsuperuser  # Create admin user
   ```

7. **Run development server**
   ```bash
   python manage.py runserver
   ```

Visit http://127.0.0.1:8000/

## Project Structure

```
eduai_platform/
├── config/                 # Django settings
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   ├── urls.py
│   └── wsgi.py
│
├── apps/                   # Django applications
│   ├── core/              # Core infrastructure
│   │   ├── middleware/    # Custom middleware
│   │   ├── utils/         # Utility functions
│   │   └── models/        # Abstract base models
│   ├── accounts/          # Auth & RBAC
│   ├── tenants/           # Multi-tenant management
│   ├── common/            # Shared models
│   └── [feature apps]     # To be implemented
│
├── frontend/              # Frontend assets
│   ├── static/
│   │   ├── js/core/      # Reusable JS utilities
│   │   └── css/
│   └── templates/
│       ├── base/         # Base templates
│       └── components/   # Reusable components
│
├── services/              # External service integrations
│   ├── ai/               # LLM & embedding services
│   └── vector_store/     # Vector database client
│
└── requirements/          # Python dependencies
```

## Core Features

### 1. Centralized API Response

All API endpoints use standardized responses:

```python
from apps.core.utils.response import APIResponse

# Success response
return APIResponse.success(data={"user_id": 123}, message="User created")

# Error response
return APIResponse.error(message="Invalid data", errors={"email": "Email already exists"})
```

### 2. Role-Based Access Control

Protect views with role decorators:

```python
from apps.core.decorators import role_required

@role_required(['teacher', 'admin'])
def teacher_dashboard(request):
    # Only teachers and admins can access
    ...
```

### 3. Frontend JavaScript Utilities

#### API Client
```javascript
// Make API calls easily
const result = await APIClient.post('/api/assignments/', {
    title: 'Homework',
    due_date: '2024-12-31'
});
```

#### Form Handler
```javascript
// Initialize auto-submit form
FormHandler.initialize(document.getElementById('my-form'), {
    onSuccess: (result) => {
        console.log('Form submitted!');
    }
});
```

#### Toast Notifications
```javascript
Toast.success('Assignment created!');
Toast.error('Something went wrong');
```

#### Modal Dialogs
```javascript
const confirmed = await Modal.confirm({
    title: 'Delete Assignment',
    message: 'Are you sure?'
});
```

## Development Guidelines

### Adding a New Feature App

1. Create app directory in `apps/`
2. Use base models from `apps.core.models.base`
3. Use `APIResponse` for all API endpoints
4. Protect views with `@role_required` decorator
5. Use frontend utilities for UI interactions

### Code Standards

- **Python**: Follow PEP 8, use type hints
- **Django**: Fat models, thin views, smart services
- **JavaScript**: ES6+, use provided utility classes
- **Commits**: Follow conventional commits

## Testing

Run tests:
```bash
python manage.py test
```

Run with coverage:
```bash
coverage run --source='.' manage.py test
coverage report
```

## Deployment

See `IMPLEMENTATION_PLAN.md` for detailed deployment instructions.

### Quick Production Setup

1. Set `DJANGO_SETTINGS_MODULE=config.settings.production`
2. Update `.env` with production values
3. Run migrations: `python manage.py migrate`
4. Collect static files: `python manage.py collectstatic`
5. Use Gunicorn: `gunicorn config.wsgi:application`

## Management Commands

```bash
# Create default roles
python manage.py create_roles

# Create a tenant
python manage.py create_tenant --name "Springfield School" --slug springfield

# Create test data
python manage.py generate_test_data
```

## API Documentation

API documentation will be available at `/api/docs/` once implemented.

## Contributing

1. Create a feature branch
2. Make your changes
3. Write/update tests
4. Submit a pull request

## License

[Your License Here]

## Support

For questions or issues, contact [your-email@example.com]

---

**Built with ❤️ for better education**
