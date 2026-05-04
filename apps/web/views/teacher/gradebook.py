"""Teacher gradebook — students × published-quests matrix.

Phase E.

- `gradebook_view`        — interactive HTML matrix.
- `gradebook_export_view` — same matrix as a CSV download.

Cells show each student's BEST score on each Assignment, expressed as %.
"-" means the student hasn't submitted that assignment yet.
"""

import csv

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.core.decorators import role_required
from apps.service.models import Assignment, Enrollment, StudentAssignment
from apps.web.views.teacher.access import (
    _teacher_classes,
    teacher_class_or_404,
)


# ---------------------------------------------------------------------------
# core builder — used by both the HTML view and the CSV export
# ---------------------------------------------------------------------------


def _build_gradebook(class_obj, sort='name'):
    """Return (rows, quests) where rows is a list of per-student dicts.

    Shape:
        rows = [
            {
              'student_id', 'name', 'email',
              'cells': [{'assignment_id', 'pct'|None, 'score', 'max_score', 'status'}],
              'submitted_count', 'avg_pct',
            },
            ...
        ]
        quests = [{'id', 'title', 'subject_name', 'due_date', 'total_marks'}]

    The cell `pct` is the BEST attempt for that student × assignment, or None
    if the student has no scored attempt yet.
    """
    enrollments = list(
        Enrollment.objects
        .filter(class_obj=class_obj, is_active=True)
        .select_related('student')
        .order_by('student__last_name', 'student__first_name')
    )

    quests = list(
        Assignment.objects
        .filter(class_obj=class_obj)
        .filter(status__in=[Assignment.STATUS_PUBLISHED, Assignment.STATUS_ARCHIVED])
        .select_related('subject')
        .order_by('due_date', 'id')
    )

    student_ids = [e.student_id for e in enrollments]
    quest_ids = [q.id for q in quests]

    # All scored attempts for these students × quests in one query.
    sa_qs = (
        StudentAssignment.objects
        .filter(student_id__in=student_ids, assignment_id__in=quest_ids)
        .values('student_id', 'assignment_id', 'score', 'max_score', 'status')
    )
    # Pick the best (highest pct) attempt per (student, assignment).
    best = {}
    for row in sa_qs:
        max_score = row['max_score'] or 0
        score = row['score'] or 0
        pct = int(round(100 * score / max_score)) if max_score else None
        key = (row['student_id'], row['assignment_id'])
        existing = best.get(key)
        if (
            existing is None
            or (pct is not None and (existing['pct'] is None or pct > existing['pct']))
        ):
            best[key] = {
                'pct': pct,
                'score': score,
                'max_score': max_score,
                'status': row['status'],
            }

    rows = []
    for e in enrollments:
        s = e.student
        cells = []
        sum_pct = 0
        n_pct = 0
        submitted_count = 0
        for q in quests:
            cell = best.get((s.id, q.id))
            if cell is None:
                cells.append({
                    'assignment_id': q.id,
                    'pct': None, 'score': None, 'max_score': q.total_marks,
                    'status': None,
                })
            else:
                cells.append({
                    'assignment_id': q.id,
                    'pct': cell['pct'],
                    'score': cell['score'],
                    'max_score': cell['max_score'],
                    'status': cell['status'],
                })
                if cell['status'] in (
                    StudentAssignment.STATUS_SUBMITTED,
                    StudentAssignment.STATUS_GRADED,
                ):
                    submitted_count += 1
                if cell['pct'] is not None:
                    sum_pct += cell['pct']
                    n_pct += 1
        rows.append({
            'student_id': s.id,
            'name': s.get_full_name() or s.email,
            'email': s.email,
            'cells': cells,
            'submitted_count': submitted_count,
            'avg_pct': int(round(sum_pct / n_pct)) if n_pct else None,
        })

    sort_keys = {
        'name': lambda r: (r['name'] or '').lower(),
        'avg': lambda r: -(r['avg_pct'] or -1),
        'submitted': lambda r: -r['submitted_count'],
    }
    rows.sort(key=sort_keys.get(sort, sort_keys['name']))

    quests_meta = [{
        'id': q.id,
        'title': q.title,
        'subject_name': q.subject.name if q.subject_id else None,
        'due_date': q.due_date,
        'total_marks': q.total_marks,
        'status': q.status,
    } for q in quests]

    return rows, quests_meta


def _resolve_class(user, class_id_raw):
    """Pick which class the teacher means.

    Priority: explicit `?class=<id>` if it's a class they teach; otherwise
    the first class in `_teacher_classes`. Returns None if the teacher has
    no classes at all.
    """
    classes = list(_teacher_classes(user))
    if not classes:
        return None, classes
    if class_id_raw:
        try:
            cid = int(class_id_raw)
        except ValueError:
            cid = None
        if cid:
            for c in classes:
                if c.id == cid:
                    return c, classes
    return classes[0], classes


# ---------------------------------------------------------------------------
# views
# ---------------------------------------------------------------------------


@login_required
@role_required(['teacher', 'school_admin'])
def gradebook_view(request):
    selected, classes = _resolve_class(request.user, request.GET.get('class'))
    sort = (request.GET.get('sort') or 'name').lower()

    rows, quests = ([], [])
    if selected:
        rows, quests = _build_gradebook(selected, sort=sort)

    return render(request, 'teacher/gradebook/index.html', {
        'user': request.user,
        'classes': classes,
        'selected_class': selected,
        'rows': rows,
        'quests': quests,
        'sort': sort,
        'active_page': 'gradebook',
    })


@login_required
@role_required(['teacher', 'school_admin'])
def gradebook_export_view(request, pk):
    """CSV: one row per student, one column per published quest."""
    cls = teacher_class_or_404(request.user, pk)
    rows, quests = _build_gradebook(cls)

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    safe_name = ''.join(ch for ch in cls.name if ch.isalnum() or ch in ('-', '_')).strip('-_')
    today = timezone.localdate().isoformat()
    response['Content-Disposition'] = (
        f'attachment; filename="gradebook-{safe_name}-{today}.csv"'
    )

    writer = csv.writer(response)
    header = ['Student', 'Email']
    for q in quests:
        header.append(f'{q["title"]} (/{q["total_marks"]})')
    header.extend(['Submitted', 'Average %'])
    writer.writerow(header)

    for r in rows:
        line = [r['name'], r['email']]
        for cell in r['cells']:
            if cell['pct'] is None:
                line.append('')
            else:
                line.append(f'{cell["score"]}/{cell["max_score"]} ({cell["pct"]}%)')
        line.append(r['submitted_count'])
        line.append(r['avg_pct'] if r['avg_pct'] is not None else '')
        writer.writerow(line)

    return response
