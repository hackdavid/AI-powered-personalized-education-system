# Quick Reference Guide - Admin Types

## 🚀 Quick Commands

### Create Django Superuser (Technical Admin)
```bash
python manage.py createsuperuser
```

### Create System Admin (Business Admin)
```bash
python manage.py create_system_admin
```

### Create Default Roles
```bash
python manage.py create_roles
```

---

## 👥 Admin Types Overview

### 1️⃣ Django Superuser (YOU - Technical Admin)
**Who:** Developers, IT Staff  
**Access:** Everything including Django Admin  
**Dashboard:** `/` → Superadmin Dashboard  

**What they can do:**
- ✅ Access Django Admin Panel (`/admin/`)
- ✅ Create/delete tenants
- ✅ Create/delete users
- ✅ Modify database directly
- ✅ Deploy code
- ✅ System configuration
- ✅ Create System Admins

**When to use:**
- Technical administration
- Database management
- Code deployment
- System configuration
- Debugging

---

### 2️⃣ System Admin (Business Admin)
**Who:** Business Managers, Operations Team  
**Access:** Business features only  
**Dashboard:** `/` → System Admin Dashboard  

**What they can do:**
- ✅ Manage tenants (via UI)
- ✅ Manage users (via UI)
- ✅ View statistics
- ✅ Generate reports
- ❌ NO Django Admin access
- ❌ NO database access

**When to use:**
- School onboarding
- User management
- Platform monitoring
- Business operations

---

### 3️⃣ School Admin
**Who:** School Administrators  
**Access:** Their school only  
**Dashboard:** `/` → School Admin Dashboard  

**What they can do:**
- ✅ Manage their school's users
- ✅ Manage classes and subjects
- ✅ Upload documents
- ✅ View school analytics
- ❌ Cannot access other schools
- ❌ NO Django Admin access

---

### 4️⃣ Teacher
**Who:** Teachers  
**Access:** Their classes only  
**Dashboard:** `/` → Teacher Dashboard  

**What they can do:**
- ✅ Create assignments
- ✅ Grade submissions
- ✅ View student progress
- ✅ Generate questions with AI
- ❌ Cannot access other teachers' classes

---

### 5️⃣ Student
**Who:** Students  
**Access:** Their own data  
**Dashboard:** `/` → Student Dashboard  

**What they can do:**
- ✅ View assignments
- ✅ Submit work
- ✅ Use AI tutor
- ✅ Track progress
- ❌ Cannot see other students' data

---

## 🔐 Access Matrix

| Feature | Superuser | System Admin | School Admin | Teacher | Student |
|---------|-----------|--------------|--------------|---------|---------|
| Django Admin | ✅ | ❌ | ❌ | ❌ | ❌ |
| Database Access | ✅ | ❌ | ❌ | ❌ | ❌ |
| All Tenants | ✅ | ✅ | ❌ | ❌ | ❌ |
| Own Tenant | ✅ | ✅ | ✅ | ✅ | ✅ |
| All Users | ✅ | ✅ | Own Tenant | Own Classes | Self |
| System Config | ✅ | ❌ | ❌ | ❌ | ❌ |
| Deploy Code | ✅ | ❌ | ❌ | ❌ | ❌ |

---

## 📝 Creating Users

### Superuser (Technical Admin)
```bash
python manage.py createsuperuser

# Enter:
Email: tech@company.com
First name: Tech
Last name: Admin
Password: ********
```

**Result:** Can access `/admin/` and everything else

---

### System Admin (Business Admin)
```bash
python manage.py create_system_admin

# Enter:
Email: business@company.com
First name: Business
Last name: Admin
Password: ********
```

**Result:** Can manage platform but NOT access `/admin/`

---

### School Admin
**Via Django Admin:**
1. Go to `/admin/`
2. Users → Add User
3. Set:
   - Email: `admin@testschool.com`
   - Role: **School Administrator**
   - Tenant: **Test School**
   - is_superuser: ❌ UNCHECKED
   - is_staff: ❌ UNCHECKED

---

### Teacher
**Via Django Admin:**
1. Go to `/admin/`
2. Users → Add User
3. Set:
   - Email: `teacher@testschool.com`
   - Role: **Teacher**
   - Tenant: **Test School**
   - is_superuser: ❌ UNCHECKED
   - is_staff: ❌ UNCHECKED

---

### Student
**Via Django Admin:**
1. Go to `/admin/`
2. Users → Add User
3. Set:
   - Email: `student@testschool.com`
   - Role: **Student**
   - Tenant: **Test School**
   - Grade Level: **8**
   - is_superuser: ❌ UNCHECKED
   - is_staff: ❌ UNCHECKED

---

## 🎯 Common Tasks

### Task: Create a new school
**Who:** Superuser or System Admin  
**How:**
- **Superuser:** Django Admin → Tenants → Add Tenant
- **System Admin:** UI (Phase 2)

---

### Task: Reset user password
**Who:** Superuser or System Admin  
**How:**
- **Superuser:** Django Admin → Users → Edit → Set password
- **System Admin:** UI (Phase 2)

---

### Task: View system health
**Who:** Any admin  
**How:** Visit `/health/` or click Health Check in dashboard

---

### Task: Deploy new code
**Who:** Superuser only  
**How:** 
```bash
git pull
pip install -r requirements/production.txt
python manage.py migrate
python manage.py collectstatic
# Restart server
```

---

### Task: Debug database issue
**Who:** Superuser only  
**How:**
```bash
python manage.py dbshell
# Or use Django Admin
```

---

## ⚠️ Security Rules

### DO:
- ✅ Use Superuser for technical tasks only
- ✅ Create System Admins for business tasks
- ✅ Limit number of Superusers (2-3 max)
- ✅ Use strong passwords
- ✅ Log all admin actions
- ✅ Regular security audits

### DON'T:
- ❌ Give Superuser to non-technical staff
- ❌ Share Superuser credentials
- ❌ Create unnecessary Superusers
- ❌ Use Superuser for routine tasks
- ❌ Give System Admin access to Django Admin

---

## 🔍 Checking User Type

### In Code:
```python
# Check Django Superuser
if user.is_superuser:
    # Full technical access
    pass

# Check System Admin (role-based)
if user.is_system_admin:
    # Business admin access
    pass

# Check School Admin
if user.is_school_admin:
    # School-level access
    pass
```

### In Template:
```django
{% if user.is_superuser %}
    <a href="/admin/">Django Admin</a>
{% endif %}

{% if user.is_system_admin %}
    <a href="/system/">System Management</a>
{% endif %}
```

---

## 📊 Dashboard URLs

| User Type | Dashboard URL | Can Access |
|-----------|---------------|------------|
| Superuser | `/` → Superadmin | Everything |
| System Admin | `/` → System Admin | Business features |
| School Admin | `/` → School Admin | Own school |
| Teacher | `/` → Teacher | Own classes |
| Student | `/` → Student | Own data |

---

## 🆘 Troubleshooting

### "Permission denied" when accessing /admin/
**Solution:** You're not a Superuser. Contact IT if you need Django Admin access.

### "No role assigned" message
**Solution:** 
1. Go to Django Admin (as Superuser)
2. Edit user
3. Assign appropriate role

### Lost Superuser password
**Solution:**
```bash
python manage.py changepassword email@example.com
```

### Need to convert System Admin to Superuser
**Solution:**
```python
# In Django Admin:
# 1. Edit user
# 2. Check "Superuser status" ✓
# 3. Check "Staff status" ✓
# 4. Save
```

---

## 📚 More Information

- **Full Documentation:** See `SUPERUSER_VS_SYSTEMADMIN.md`
- **Setup Guide:** See `START_HERE.md`
- **Testing Guide:** See `SETUP_AND_TEST.md`

---

**Remember:** Superuser = Technical, System Admin = Business. Keep them separate! 🔐
