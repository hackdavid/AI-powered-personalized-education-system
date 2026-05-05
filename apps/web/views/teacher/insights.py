"""Teacher Insights Dashboard - Phase F.

Provides data-driven insights for teachers:
- Struggling students queue (auto-flagged based on risk factors)
- Top performers spotlight (leaderboard by different metrics)
- Mastery heatmap (class-wide subject mastery visualization)
"""

from collections import defaultdict
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, ExpressionWrapper, F, FloatField, Q
from django.shortcuts import render
from django.utils import timezone

from apps.core.decorators import role_required
from apps.service.models import (
    Enrollment,
    StudentAssignment,
    StudentProfile,
    Subject,
)
from apps.web.views.teacher.access import _teacher_classes


# ---------------------------------------------------------------------------
# Struggling Students Detection
# ---------------------------------------------------------------------------


def _identify_struggling_students(class_obj):
    """Identify at-risk students based on multiple risk factors.

    Risk factors:
    1. Low mastery (avg < 40%)
    2. Inactive for 3+ days
    3. Broken streak (streak_days = 0 or very low)
    4. Low quest performance

    Returns list of dicts with student info + risk factors.
    """
    now = timezone.now()
    three_days_ago = now - timedelta(days=3)

    # Get all students in this class
    enrollments = Enrollment.objects.filter(
        class_obj=class_obj, is_active=True
    ).select_related('student', 'student__profile')

    struggling = []

    for e in enrollments:
        student = e.student
        profile = getattr(student, 'profile', None)
        if not profile:
            continue

        risk_factors = []
        risk_score = 0

        # Factor 1: Low mastery
        avg_mastery = _calculate_avg_mastery(profile)
        if avg_mastery is not None and avg_mastery < 40:
            risk_factors.append(f'Low mastery ({avg_mastery}%)')
            risk_score += 3

        # Factor 2: Inactive
        if profile.last_active_date and profile.last_active_date < three_days_ago.date():
            days_inactive = (now.date() - profile.last_active_date).days
            risk_factors.append(f'Inactive {days_inactive} days')
            risk_score += 2

        # Factor 3: Broken streak
        if profile.streak_days == 0:
            risk_factors.append('Streak broken')
            risk_score += 1
        elif profile.streak_days < 3:
            risk_factors.append(f'Low streak ({profile.streak_days} days)')
            risk_score += 1

        # Factor 4: Low quest performance
        avg_quest_score = _calculate_avg_quest_score(student)
        if avg_quest_score is not None and avg_quest_score < 50:
            risk_factors.append(f'Avg quest score {avg_quest_score}%')
            risk_score += 2

        # Only flag if there are at least 2 risk factors
        if len(risk_factors) >= 2:
            struggling.append({
                'student': student,
                'profile': profile,
                'risk_score': risk_score,
                'risk_factors': risk_factors,
                'avg_mastery': avg_mastery,
                'days_inactive': (now.date() - profile.last_active_date).days if profile.last_active_date else None,
                'streak_days': profile.streak_days,
                'total_xp': profile.total_xp,
            })

    # Sort by risk score (highest risk first)
    struggling.sort(key=lambda x: -x['risk_score'])

    return struggling


def _calculate_avg_mastery(profile):
    """Calculate average mastery across all subjects."""
    if not profile.mastery_per_subject:
        return None

    values = [v for v in profile.mastery_per_subject.values() if v is not None]
    if not values:
        return None

    return int(round(sum(values) / len(values)))


def _calculate_avg_quest_score(student):
    """Calculate average quest score (percentage) for graded assignments."""
    graded = StudentAssignment.objects.filter(
        student=student,
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

    return int(round(graded)) if graded is not None else None


# ---------------------------------------------------------------------------
# Top Performers
# ---------------------------------------------------------------------------


def _get_top_performers(class_obj, metric='xp', limit=10):
    """Get top performing students by specified metric.

    Metrics:
    - 'xp': Total XP
    - 'mastery': Average mastery
    - 'streak': Longest streak
    - 'quest_score': Average quest score
    """
    enrollments = Enrollment.objects.filter(
        class_obj=class_obj, is_active=True
    ).select_related('student', 'student__profile')

    performers = []

    for e in enrollments:
        student = e.student
        profile = getattr(student, 'profile', None)
        if not profile:
            continue

        data = {
            'student': student,
            'profile': profile,
            'total_xp': profile.total_xp,
            'streak_days': profile.streak_days,
            'avg_mastery': _calculate_avg_mastery(profile),
            'avg_quest_score': _calculate_avg_quest_score(student),
            'level': profile.level,
            'rank': profile.rank,
        }

        performers.append(data)

    # Sort by metric
    if metric == 'xp':
        performers.sort(key=lambda x: -x['total_xp'])
    elif metric == 'mastery':
        performers.sort(key=lambda x: -(x['avg_mastery'] or -1))
    elif metric == 'streak':
        performers.sort(key=lambda x: -x['streak_days'])
    elif metric == 'quest_score':
        performers.sort(key=lambda x: -(x['avg_quest_score'] or -1))

    return performers[:limit]


# ---------------------------------------------------------------------------
# Mastery Heatmap
# ---------------------------------------------------------------------------


def _build_mastery_heatmap(class_obj):
    """Build mastery heatmap: students × subjects matrix.

    Returns:
        students: list of student dicts
        subjects: list of subjects
        matrix: dict[(student_id, subject_id)] = percentage
        averages: dict[subject_id] = avg percentage across class
    """
    # Get subjects for this tenant
    subjects = list(Subject.objects.filter(tenant=class_obj.tenant).order_by('name'))
    subject_ids = [s.id for s in subjects]

    # Get students in this class
    enrollments = Enrollment.objects.filter(
        class_obj=class_obj, is_active=True
    ).select_related('student', 'student__profile').order_by('student__last_name', 'student__first_name')

    students = []
    matrix = {}
    subject_totals = defaultdict(lambda: {'sum': 0, 'count': 0})

    for e in enrollments:
        student = e.student
        profile = getattr(student, 'profile', None)

        student_data = {
            'id': student.id,
            'name': student.get_full_name() or student.email,
            'profile': profile,
        }
        students.append(student_data)

        # Extract mastery per subject
        if profile and profile.mastery_per_subject:
            for subject in subjects:
                subject_id_str = str(subject.id)
                mastery = profile.mastery_per_subject.get(subject_id_str)

                if mastery is not None:
                    matrix[(student.id, subject.id)] = int(mastery)
                    subject_totals[subject.id]['sum'] += mastery
                    subject_totals[subject.id]['count'] += 1

    # Calculate averages per subject
    averages = {}
    for subject in subjects:
        total = subject_totals[subject.id]
        if total['count'] > 0:
            averages[subject.id] = int(round(total['sum'] / total['count']))
        else:
            averages[subject.id] = None

    return {
        'students': students,
        'subjects': subjects,
        'matrix': matrix,
        'averages': averages,
    }


# ---------------------------------------------------------------------------
# Main Insights View
# ---------------------------------------------------------------------------


@login_required
@role_required(['teacher', 'school_admin'])
def insights_view(request):
    """Teacher insights dashboard with all three components."""
    # Get teacher's classes
    classes = list(_teacher_classes(request.user))

    if not classes:
        return render(request, 'teacher/insights/index.html', {
            'user': request.user,
            'no_classes': True,
            'active_page': 'insights',
        })

    # Class filter
    selected_class_id = request.GET.get('class')
    try:
        selected_class_id = int(selected_class_id) if selected_class_id else None
    except ValueError:
        selected_class_id = None

    # Default to first class
    if selected_class_id:
        selected_class = next((c for c in classes if c.id == selected_class_id), classes[0])
    else:
        selected_class = classes[0]

    # Metric for top performers
    metric = request.GET.get('metric', 'xp')
    if metric not in ['xp', 'mastery', 'streak', 'quest_score']:
        metric = 'xp'

    # Build all three insights
    struggling_students = _identify_struggling_students(selected_class)
    top_performers = _get_top_performers(selected_class, metric=metric, limit=10)
    heatmap_data = _build_mastery_heatmap(selected_class)

    # Calculate class-level stats
    total_students = Enrollment.objects.filter(
        class_obj=selected_class, is_active=True
    ).count()

    return render(request, 'teacher/insights/index.html', {
        'user': request.user,
        'classes': classes,
        'selected_class': selected_class,
        'total_students': total_students,
        'struggling_students': struggling_students,
        'struggling_count': len(struggling_students),
        'top_performers': top_performers,
        'metric': metric,
        'heatmap_students': heatmap_data['students'],
        'heatmap_subjects': heatmap_data['subjects'],
        'heatmap_matrix': heatmap_data['matrix'],
        'heatmap_averages': heatmap_data['averages'],
        'active_page': 'insights',
    })
