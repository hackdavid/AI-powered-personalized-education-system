# Complete Setup and Testing Guide

## Quick Setup (5 minutes)

### 1. Navigate to Project

```bash
cd "C:\Users\DaudDewan\OneDrive - SymphonyAI\Documents\Learning\roehampton\ai_engineering\code_base\eduai_platform"
```

### 2. Create Virtual Environment

```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements\development.txt
```

### 4. Copy Environment File

```bash
copy .env.example .env
```

Edit `.env` and set a secret key (or leave default for development):
```
DJANGO_SECRET_KEY=your-secret-key-change-this
DJANGO_DEBUG=True
```

### 5. Run Migrations

```bash
python manage.py migrate
```

### 6. Create Default Roles

```bash
python manage.py create_roles
```

You should see:
```
Creating default roles and permissions...
  ✓ Created permission: View Assignments
  ✓ Created permission: Submit Assignments
  ...
✓ Created role: Student
  Assigned 5 permissions
✓ Created role: Teacher
  Assigned 6 permissions
✓ Created role: School Administrator
  Assigned 12 permissions
✓ Created role: System Administrator
  Assigned 19 permissions
```

### 7. Create Superuser

```bash
python manage.py createsuperuser
```

Enter:
- Email: `admin@test.com`
- First name: `System`
- Last name: `Admin`
- Password: (your password)

### 8. Run Development Server

```bash
python manage.py runserver
```

## Testing the Flow

### Step 1: Visit Landing Page

1. Open browser: http://127.0.0.1:8000/
2. You should see:
   - ✅ Beautiful landing page
   - ✅ Navigation bar with "Login" button
   - ✅ Features section
   - ✅ Technology section
   - ✅ Call-to-action
   - ✅ Footer

### Step 2: Access Django Admin

1. Go to: http://127.0.0.1:8000/admin/
2. Login with superuser credentials (`admin@test.com`)
3. You should see Django admin panel

### Step 3: Create a Tenant (School)

In Django Admin:

1. Click **Tenants** → **Add Tenant**
2. Fill in:
   ```
   Name: Test School
   Slug: testschool
   Is Active: ✓
   Subscription tier: Free
   Max students: 100
   Max teachers: 10
   ```
3. Click **Save**

### Step 4: Create Test Users

#### Create Student User:

1. Go to **Users** → **Add User**
2. Fill in:
   ```
   Email: student@test.com
   First name: John
   Last name: Doe
   Password: testpass123
   Tenant: Test School
   Role: Student
   Grade Level: 8
   Is Active: ✓
   ```
3. Save

#### Create Teacher User:

1. Go to **Users** → **Add User**
2. Fill in:
   ```
   Email: teacher@test.com
   First name: Jane
   Last name: Smith
   Password: testpass123
   Tenant: Test School
   Role: Teacher
   Is Active: ✓
   ```
3. Save

#### Create School Admin User:

1. Go to **Users** → **Add User**
2. Fill in:
   ```
   Email: schooladmin@test.com
   First name: Robert
   Last name: Johnson
   Password: testpass123
   Tenant: Test School
   Role: School Administrator
   Is Active: ✓
   ```
3. Save

### Step 5: Test Login Flow

#### Test as Student:

1. **Logout** from admin (top right)
2. Go to: http://127.0.0.1:8000/
3. Click **Login** button
4. Login with:
   ```
   Email: student@test.com
   Password: testpass123
   ```
5. ✅ Should redirect to **Student Dashboard** showing:
   - Welcome message with student name
   - Sidebar with student navigation
   - Pending assignments (0)
   - Active goals (0)
   - Total XP (0)
   - User dropdown in navbar

#### Test as Teacher:

1. **Logout** (click user dropdown → Logout)
2. Go to: http://127.0.0.1:8000/auth/login/
3. Login with:
   ```
   Email: teacher@test.com
   Password: testpass123
   ```
4. ✅ Should redirect to **Teacher Dashboard** showing:
   - Welcome message with teacher name
   - Sidebar with teacher navigation
   - Total students (0)
   - Active assignments (0)
   - Pending reviews (0)

#### Test as School Admin:

1. **Logout**
2. Go to: http://127.0.0.1:8000/auth/login/
3. Login with:
   ```
   Email: schooladmin@test.com
   Password: testpass123
   ```
4. ✅ Should redirect to **School Admin Dashboard** showing:
   - School name (Test School)
   - User management options
   - School statistics
   - School information

#### Test as System Admin:

1. **Logout**
2. Go to: http://127.0.0.1:8000/auth/login/
3. Login with:
   ```
   Email: admin@test.com
   Password: (your superuser password)
   ```
4. ✅ Should redirect to **System Admin Dashboard** showing:
   - System-wide statistics
   - Link to Django admin
   - Health check option

### Step 6: Test Navigation

While logged in:

1. ✅ Click on **Dashboard** - Should go to dashboard
2. ✅ Click user avatar dropdown - Should show:
   - User name and email
   - Profile option
   - Change Password option
   - Logout option
3. ✅ Click **Logout** - Should redirect to login page
4. ✅ Go to home page while logged in - Should show navbar with "Dashboard" button

### Step 7: Test Health Check

Visit: http://127.0.0.1:8000/health/

Should return:
```json
{
  "status": "healthy",
  "checks": {
    "database": {
      "healthy": true,
      "message": "Database connection OK"
    },
    "timestamp": "2024-04-16T..."
  }
}
```

## What to Verify

### ✅ Landing Page Flow:
- [ ] Landing page loads with beautiful design
- [ ] Navigation bar shows with Login button
- [ ] All sections visible (Hero, Features, Technology, CTA)
- [ ] Footer displays properly
- [ ] "Get Started" button goes to login
- [ ] Smooth scrolling to sections works

### ✅ Login Flow:
- [ ] Login page has beautiful design
- [ ] Can login with email and password
- [ ] "Remember me" checkbox works
- [ ] Shows demo accounts for reference
- [ ] Redirects to correct dashboard based on role

### ✅ Dashboard Access:
- [ ] Student sees student dashboard
- [ ] Teacher sees teacher dashboard
- [ ] School admin sees school admin dashboard
- [ ] System admin sees system admin dashboard
- [ ] Each dashboard shows correct sidebar navigation
- [ ] User info displays in navbar

### ✅ Role-Based Features:
- [ ] Students see assignments and AI tutor links
- [ ] Teachers see analytics and class management
- [ ] School admins see user management
- [ ] System admins see all tenants

### ✅ Security:
- [ ] Cannot access other role's features
- [ ] Must be logged in to access dashboards
- [ ] Logout works properly
- [ ] Session management works

## Troubleshooting

### Issue: "No module named 'apps'"

**Solution:**
```bash
# Make sure you're in the correct directory
cd eduai_platform
# And virtual environment is activated
venv\Scripts\activate
```

### Issue: "Table doesn't exist"

**Solution:**
```bash
python manage.py migrate
```

### Issue: "Role not found"

**Solution:**
```bash
python manage.py create_roles
```

### Issue: Static files not loading

**Solution:**
```bash
python manage.py collectstatic --noinput
```

### Issue: "Invalid password"

**Solution:**
- Password must be at least 8 characters
- Cannot be too similar to email
- Cannot be entirely numeric

## Next Steps

Now that Phase 1 is complete and tested, you can:

1. **Add More Data:**
   - Create subjects (Math, English, Science)
   - Create classes (Grade 8-A, Grade 9-B)
   - Assign teachers to classes

2. **Start Phase 2:**
   - Implement AI services
   - Create document ingestion pipeline
   - Build RAG-based tutoring

3. **Customize:**
   - Update tenant branding (logo, colors)
   - Modify dashboard widgets
   - Add custom permissions

## Success! 🎉

You now have a fully functional multi-tenant education platform with:
- ✅ Beautiful landing page
- ✅ Role-based authentication
- ✅ 4 different dashboard types
- ✅ Multi-tenant architecture
- ✅ Complete RBAC system
- ✅ Production-ready foundation

Ready to build amazing education features! 🚀
