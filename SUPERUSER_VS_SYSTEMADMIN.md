# Django Superuser vs System Admin

## Overview

The EduAI Platform has two types of top-level administrators:

1. **Django Superuser** (Technical Admin)
2. **System Admin** (Business Admin)

This separation ensures security and proper access control.

## Comparison

| Feature | Django Superuser | System Admin |
|---------|-----------------|--------------|
| **Purpose** | Technical administration | Business administration |
| **Django Admin Access** | ✅ Yes (Full) | ❌ No |
| **Database Access** | ✅ Direct | ❌ No |
| **Manage Tenants** | ✅ Yes (via Django Admin) | ✅ Yes (via UI) |
| **Manage Users** | ✅ Yes (all users) | ✅ Yes (via UI) |
| **System Configuration** | ✅ Full access | ⚠️ Limited |
| **Code Deployment** | ✅ Can deploy | ❌ Cannot |
| **Server Access** | ✅ Usually yes | ❌ No |
| **Role Assignment** | `is_superuser = True` | `role = system_admin` |
| **Staff Status** | `is_staff = True` | `is_staff = False` |
| **Who Should Have** | Developers, Tech Team | Business Managers |

## When to Use Each

### Use Django Superuser When:
- You need to access Django Admin panel
- You need to modify database directly
- You need to install packages or deploy code
- You're a developer or technical administrator
- You need to debug system issues
- You need to manage Django settings

### Use System Admin When:
- You need to manage multiple schools (tenants)
- You need to oversee platform usage
- You're a business administrator (not technical)
- You need to create/manage users across tenants
- You need to view system-wide statistics
- You don't need Django Admin access

## Creating Each Type

### Creating Django Superuser

```bash
# Method 1: Management Command (Recommended)
python manage.py createsuperuser

# Enter:
# Email: tech.admin@company.com
# First name: Tech
# Last name: Admin
# Password: (secure password)

# Method 2: Django Admin (if you already have superuser)
# 1. Go to /admin/
# 2. Users → Add User
# 3. Check "Superuser status" ✓
# 4. Check "Staff status" ✓
# 5. Role: (any or none)
```

### Creating System Admin

```bash
# Method 1: Management Command (Recommended)
python manage.py create_system_admin

# Enter:
# Email: business.admin@company.com
# First name: Business
# Last name: Admin
# Password: (secure password)

# Method 2: Django Admin
# 1. Go to /admin/
# 2. Users → Add User
# 3. Role: System Administrator
# 4. Superuser status: ❌ UNCHECKED
# 5. Staff status: ❌ UNCHECKED
# 6. Tenant: (leave blank)
```

## Login Behavior

### Django Superuser Login:
```
1. Visit /auth/login/
2. Enter superuser credentials
3. Redirected to: Superadmin Dashboard
4. Can click "Django Admin Panel" to access /admin/
```

### System Admin Login:
```
1. Visit /auth/login/
2. Enter system admin credentials
3. Redirected to: System Admin Dashboard
4. Cannot access /admin/ (will get permission denied)
```

## Dashboard Differences

### Superadmin Dashboard:
- ✅ Link to Django Admin Panel
- ✅ System Health Check
- ✅ Technical system information
- ✅ Create System Admins
- ✅ Database management
- ✅ Full configuration access

### System Admin Dashboard:
- ✅ Tenant management (via UI)
- ✅ User management (via UI)
- ✅ System-wide statistics
- ✅ Business reports
- ❌ No Django Admin link
- ❌ No database access
- ❌ No technical configuration

## Security Best Practices

### For Django Superuser:
1. ✅ Only create for technical staff
2. ✅ Use strong, unique passwords
3. ✅ Enable 2FA (when implemented)
4. ✅ Limit the number of superusers (2-3 max)
5. ✅ Never share credentials
6. ✅ Log all superuser actions
7. ✅ Regular security audits

### For System Admin:
1. ✅ Create for business managers
2. ✅ Use strong passwords
3. ✅ Can have multiple system admins
4. ✅ Cannot access sensitive technical areas
5. ✅ Cannot modify system configuration
6. ✅ Actions are logged
7. ✅ Can be revoked easily

## Example Scenarios

### Scenario 1: New School Onboarding
**Who:** System Admin  
**Why:** Business operation, doesn't need technical access  
**What:** Create tenant, add school admin, configure settings

### Scenario 2: Database Migration
**Who:** Django Superuser  
**Why:** Technical operation requiring direct database access  
**What:** Run migrations, backup database, verify integrity

### Scenario 3: User Support Issue
**Who:** System Admin  
**Why:** Can manage users without technical access  
**What:** Reset password, update role, check account status

### Scenario 4: System Configuration
**Who:** Django Superuser  
**Why:** Requires Django settings modification  
**What:** Update email settings, modify middleware, change database

### Scenario 5: Platform Usage Report
**Who:** System Admin  
**Why:** Business reporting  
**What:** View statistics, generate reports, monitor usage

### Scenario 6: Code Deployment
**Who:** Django Superuser  
**Why:** Technical deployment task  
**What:** Deploy new version, run migrations, update dependencies

## Checking User Type

### In Python Code:
```python
# Check if Django superuser
if user.is_superuser:
    # Technical admin
    pass

# Check if System Admin (role-based)
if user.is_system_admin:
    # Business admin
    pass

# Check if either
if user.is_superuser or user.is_system_admin:
    # Any system-level admin
    pass
```

### In Templates:
```django
{% if user.is_superuser %}
    <!-- Django Superuser only -->
    <a href="/admin/">Django Admin</a>
{% endif %}

{% if user.is_system_admin %}
    <!-- System Admin only -->
    <a href="/system/tenants/">Manage Tenants</a>
{% endif %}
```

## Migration Path

### Converting Superuser to System Admin:
```python
# In Django Admin:
# 1. Open the user
# 2. Uncheck "Superuser status"
# 3. Uncheck "Staff status"
# 4. Set Role to "System Administrator"
# 5. Save

# Or via Django shell:
from apps.accounts.models import User, Role

user = User.objects.get(email='user@example.com')
system_admin_role = Role.objects.get(name='system_admin')

user.is_superuser = False
user.is_staff = False
user.role = system_admin_role
user.save()
```

### Converting System Admin to Superuser:
```python
# In Django Admin:
# 1. Open the user
# 2. Check "Superuser status" ✓
# 3. Check "Staff status" ✓
# 4. Save

# Or via Django shell:
from apps.accounts.models import User

user = User.objects.get(email='user@example.com')
user.is_superuser = True
user.is_staff = True
user.save()
```

## FAQs

### Q: Can a user be both Superuser and have System Admin role?
**A:** Technically yes, but not recommended. Superuser already has all permissions. If a user is a superuser, they'll see the Superadmin dashboard regardless of their role.

### Q: Can System Admin access Django Admin?
**A:** No. System Admins have `is_staff=False`, which prevents Django Admin access.

### Q: Which one should I use for day-to-day operations?
**A:** System Admin. Reserve Superuser for technical tasks only.

### Q: Can I have multiple Superusers?
**A:** Yes, but limit it to 2-3 trusted technical staff members.

### Q: Can I have multiple System Admins?
**A:** Yes, you can have as many as needed for business operations.

### Q: What happens if I forget superuser password?
**A:** Run `python manage.py changepassword email@example.com` with server access.

### Q: Can System Admin create other System Admins?
**A:** Not directly. They can request a Superuser to create one, or use a management interface (Phase 2).

## Summary

| Aspect | Django Superuser | System Admin |
|--------|-----------------|--------------|
| **Access Level** | Technical + Business | Business Only |
| **Risk Level** | High | Medium |
| **Number Needed** | 1-3 | Many |
| **For Who** | Developers | Managers |
| **Can Access Admin** | Yes | No |
| **Can Deploy Code** | Yes | No |

**Key Takeaway:** Django Superuser = Technical Admin, System Admin = Business Admin. Keep them separate for better security!

---

**Best Practice:** Always use System Admin for business operations and reserve Superuser for technical administration only.
