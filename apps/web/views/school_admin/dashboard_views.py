"""School Admin Dashboard and Analytics.

Provides school-wide overview, analytics, and management tools for administrators:
- Main dashboard with key metrics and alerts
- School-wide analytics (enrollment trends, performance, teacher utilization)
- Teacher performance monitoring
- Alerts and recommendations
"""

from collections import defaultdict
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, ExpressionWrapper, F, FloatField, Q
from django.shortcuts import render
from django.utils import timezone

from apps.accounts.models import User
from apps.core.decorators import role_required
from apps.service.models import (
    Assignment,
    Class,
    ClassSubject,
    Enrollment,
    StudentAssignment,
    StudentProfile,
    Subject,
)


# ---------------------------------------------------------------------------
# Dashboard Metrics
# ---------------------------------------------------------------------------


def _get_dashboard_stats(tenant):
    """Calculate key metrics for dashboard stats cards."""
    now = timezone.now()
    week_ago = now - timedelta(days=7)

    stats = {
        # Core counts
        'total_students': User.objects.filter(
            tenant=tenant, role__name='student', is_active=True
        ).count(),
        'total_teachers': User.objects.filter(
            tenant=tenant, role__name='teacher', is_active=True
        ).count(),
        'total_classes': Class.objects.filter(tenant=tenant, is_active=True).count(),
        'total_subjects': Subject.objects.filter(tenant=tenant).count(),

        # Active items
        'active_quests': Assignment.objects.filter(
            tenant=tenant,
            status=Assignment.STATUS_PUBLISHED,
            due_date__gte=now,
        ).count(),

        # Recent activity
        'students_added_this_week': User.objects.filter(
            tenant=tenant,
            role__name='student',
            created_at__gte=week_ago,
        ).count(),
        'teachers_added_this_week': User.objects.filter(
            tenant=tenant,
            role__name='teacher',
            created_at__gte=week_ago,
        ).count(),
        'classes_created_this_week': Class.objects.filter(
            tenant=tenant,
            created_at__gte=week_ago,
        ).count(),

        # Engagement
        'submissions_this_week': StudentAssignment.objects.filter(
            assignment__tenant=tenant,
            submitted_at__gte=week_ago,
        ).count(),
    }

    return stats


def _get_recent_activity(tenant, limit=10):
    """Get recent activity feed items."""
    activities = []

    # Recent students
    recent_students = User.objects.filter(
        tenant=tenant, role__name='student'
    ).order_by('-created_at')[:limit]

    for student in recent_students:
        activities.append({
            'type': 'student_added',
            'icon': 'user-plus',
            'text': f'Student {student.get_full_name()} enrolled',
            'timestamp': student.created_at,
        })

    # Recent teachers
    recent_teachers = User.objects.filter(
        tenant=tenant, role__name='teacher'
    ).order_by('-created_at')[:limit]

    for teacher in recent_teachers:
        activities.append({
            'type': 'teacher_added',
            'icon': 'user-check',
            'text': f'Teacher {teacher.get_full_name()} added',
            'timestamp': teacher.created_at,
        })

    # Recent classes
    recent_classes = Class.objects.filter(
        tenant=tenant
    ).order_by('-created_at')[:limit]

    for cls in recent_classes:
        activities.append({
            'type': 'class_created',
            'icon': 'book',
            'text': f'Class {cls.name} created',
            'timestamp': cls.created_at,
        })

    # Sort by timestamp
    activities.sort(key=lambda x: x['timestamp'], reverse=True)

    return activities[:limit]


def _get_alerts(tenant):
    """Generate alerts for admin attention."""
    alerts = []

    # Alert 1: Classes with no teacher
    classes_no_teacher = Class.objects.filter(
        tenant=tenant, is_active=True, class_teacher__isnull=True
    ).count()

    if classes_no_teacher > 0:
        alerts.append({
            'level': 'warning',
            'icon': 'alert-triangle',
            'message': f'{classes_no_teacher} class{"es" if classes_no_teacher != 1 else ""} have no teacher assigned',
            'action_text': 'Assign Teachers',
            'action_url': '/school-admin/classes/',
        })

    # Alert 2: Students not enrolled
    students_not_enrolled = User.objects.filter(
        tenant=tenant, role__name='student', is_active=True
    ).exclude(
        class_enrollments__is_active=True
    ).count()

    if students_not_enrolled > 0:
        alerts.append({
            'level': 'warning',
            'icon': 'user-x',
            'message': f'{students_not_enrolled} student{"s" if students_not_enrolled != 1 else ""} not enrolled in any class',
            'action_text': 'Manage Enrollment',
            'action_url': '/school-admin/enrollment/',
        })

    # Alert 3: Inactive teachers (no login in 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    inactive_teachers = User.objects.filter(
        tenant=tenant,
        role__name='teacher',
        is_active=True,
        last_login__lt=thirty_days_ago,
    ).count()

    if inactive_teachers > 0:
        alerts.append({
            'level': 'info',
            'icon': 'user-minus',
            'message': f'{inactive_teachers} teacher{"s" if inactive_teachers != 1 else ""} inactive for 30+ days',
            'action_text': 'View Teachers',
            'action_url': '/school-admin/teachers/',
        })

    # Alert 4: Oversized classes
    oversized_classes = Class.objects.filter(
        tenant=tenant, is_active=True
    ).annotate(
        student_count=Count('enrollments', filter=Q(enrollments__is_active=True))
    ).filter(student_count__gt=35)

    if oversized_classes.count() > 0:
        alerts.append({
            'level': 'info',
            'icon': 'users',
            'message': f'{oversized_classes.count()} class{"es" if oversized_classes.count() != 1 else ""} have 35+ students',
            'action_text': 'View Classes',
            'action_url': '/school-admin/classes/',
        })

    return alerts


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


def _get_enrollment_trends(tenant):
    """Calculate enrollment trends over time."""
    # Get enrollment counts by month for last 6 months
    six_months_ago = timezone.now() - timedelta(days=180)

    students_by_month = User.objects.filter(
        tenant=tenant,
        role__name='student',
        created_at__gte=six_months_ago,
    ).extra(
        select={'month': 'EXTRACT(month FROM accounts_user.created_at)'}
    ).values('month').annotate(count=Count('id')).order_by('month')

    return list(students_by_month)


def _get_teacher_utilization(tenant):
    """Calculate teacher workload distribution."""
    teachers = User.objects.filter(
        tenant=tenant, role__name='teacher', is_active=True
    )

    utilization = []

    for teacher in teachers:
        # Count classes as homeroom teacher
        homeroom_classes = Class.objects.filter(
            tenant=tenant, class_teacher=teacher, is_active=True
        ).count()

        # Count classes via ClassSubject
        subject_classes = ClassSubject.objects.filter(
            teacher=teacher
        ).values('class_obj').distinct().count()

        total_classes = max(homeroom_classes, subject_classes)

        # Count students
        student_count = Enrollment.objects.filter(
            class_obj__tenant=tenant,
            class_obj__class_teacher=teacher,
            is_active=True,
        ).values('student').distinct().count()

        # Count quests published
        quests_published = Assignment.objects.filter(
            tenant=tenant,
            created_by=teacher,
            status=Assignment.STATUS_PUBLISHED,
        ).count()

        utilization.append({
            'teacher': teacher,
            'classes': total_classes,
            'students': student_count,
            'quests_published': quests_published,
            'last_login': teacher.last_login,
        })

    # Sort by classes (descending)
    utilization.sort(key=lambda x: -x['classes'])

    return utilization


def _get_class_performance(tenant):
    """Compare performance across all classes."""
    classes = Class.objects.filter(tenant=tenant, is_active=True)

    performance = []

    for cls in classes:
        # Get students in this class
        student_ids = list(
            Enrollment.objects.filter(
                class_obj=cls, is_active=True
            ).values_list('student_id', flat=True)
        )

        if not student_ids:
            continue

        # Calculate average mastery
        profiles = StudentProfile.objects.filter(student_id__in=student_ids)
        total_mastery = 0
        mastery_count = 0

        for profile in profiles:
            if profile.mastery_per_subject:
                for mastery in profile.mastery_per_subject.values():
                    if mastery is not None:
                        total_mastery += mastery
                        mastery_count += 1

        avg_mastery = int(total_mastery / mastery_count) if mastery_count else None

        # Calculate average quest score
        avg_quest_score = StudentAssignment.objects.filter(
            student_id__in=student_ids,
            status=StudentAssignment.STATUS_GRADED,
            max_score__gt=0,
        ).aggregate(
            avg=Avg(
                ExpressionWrapper(
                    F('score') * 100.0 / F('max_score'),
                    output_field=FloatField(),
                )
            )
        )['avg']

        avg_quest_score = int(avg_quest_score) if avg_quest_score else None

        # Submission rate (last 7 days)
        week_ago = timezone.now() - timedelta(days=7)
        submissions = StudentAssignment.objects.filter(
            student_id__in=student_ids,
            submitted_at__gte=week_ago,
        ).count()

        performance.append({
            'class': cls,
            'student_count': len(student_ids),
            'avg_mastery': avg_mastery,
            'avg_quest_score': avg_quest_score,
            'submissions_this_week': submissions,
            'teacher': cls.class_teacher,
        })

    # Sort by mastery (descending)
    performance.sort(key=lambda x: -(x['avg_mastery'] or -1))

    return performance


def _get_subject_distribution(tenant):
    """Get subject usage statistics."""
    subjects = Subject.objects.filter(tenant=tenant)

    distribution = []

    for subject in subjects:
        # Count classes teaching this subject
        class_count = ClassSubject.objects.filter(subject=subject).count()

        # Calculate average mastery for this subject across all students
        all_profiles = StudentProfile.objects.filter(student__tenant=tenant)
        total_mastery = 0
        mastery_count = 0

        for profile in all_profiles:
            if profile.mastery_per_subject:
                subject_mastery = profile.mastery_per_subject.get(str(subject.id))
                if subject_mastery is not None:
                    total_mastery += subject_mastery
                    mastery_count += 1

        avg_mastery = int(total_mastery / mastery_count) if mastery_count else None

        distribution.append({
            'subject': subject,
            'class_count': class_count,
            'avg_mastery': avg_mastery,
        })

    # Sort by class count (descending)
    distribution.sort(key=lambda x: -x['class_count'])

    return distribution


# ---------------------------------------------------------------------------
# Main Views
# ---------------------------------------------------------------------------


@login_required
@role_required(['school_admin'])
def admin_dashboard_view(request):
    """School admin main dashboard."""
    tenant = request.user.tenant

    stats = _get_dashboard_stats(tenant)
    recent_activity = _get_recent_activity(tenant, limit=8)
    alerts = _get_alerts(tenant)

    return render(request, 'school_admin/dashboard.html', {
        'user': request.user,
        'stats': stats,
        'recent_activity': recent_activity,
        'alerts': alerts,
        'active_page': 'dashboard',
    })


@login_required
@role_required(['school_admin'])
def admin_analytics_view(request):
    """School-wide analytics and insights."""
    tenant = request.user.tenant

    enrollment_trends = _get_enrollment_trends(tenant)
    teacher_utilization = _get_teacher_utilization(tenant)
    class_performance = _get_class_performance(tenant)
    subject_distribution = _get_subject_distribution(tenant)

    return render(request, 'school_admin/analytics.html', {
        'user': request.user,
        'enrollment_trends': enrollment_trends,
        'teacher_utilization': teacher_utilization,
        'class_performance': class_performance,
        'subject_distribution': subject_distribution,
        'active_page': 'analytics',
    })


@login_required
@role_required(['school_admin'])
def enrollment_management_view(request):
    """Manage student enrollments."""
    tenant = request.user.tenant

    # Students not enrolled in any class
    unenrolled_students = User.objects.filter(
        tenant=tenant,
        role__name='student',
        is_active=True,
    ).exclude(
        class_enrollments__is_active=True
    ).order_by('last_name', 'first_name')

    # All classes
    classes = Class.objects.filter(tenant=tenant, is_active=True).order_by('name')

    # Class sizes
    class_sizes = []
    for cls in classes:
        size = Enrollment.objects.filter(class_obj=cls, is_active=True).count()
        class_sizes.append({
            'class': cls,
            'size': size,
            'status': 'over' if size > 35 else 'optimal' if size >= 20 else 'under',
        })

    return render(request, 'school_admin/enrollment.html', {
        'user': request.user,
        'unenrolled_students': unenrolled_students,
        'class_sizes': class_sizes,
        'active_page': 'enrollment',
    })
