"""Teacher grading interface for student quest submissions.

Phase F: Grading

Teachers can grade student submissions by:
- Viewing the student's answers alongside questions
- Assigning marks per question
- Adding feedback per question
- Submitting the grade to mark as GRADED
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.core.decorators import role_required
from apps.service.models import Answer, Question, StudentAssignment
from apps.web.views.teacher.access import _teacher_classes


def _teacher_can_grade_submission(user, student_assignment):
    """Check if the teacher can grade this submission.

    Returns True if the student_assignment's class is taught by this teacher.
    """
    teacher_class_ids = [c.id for c in _teacher_classes(user)]
    return student_assignment.assignment.class_obj_id in teacher_class_ids


@login_required
@role_required(['teacher', 'school_admin'])
def grading_view(request, pk):
    """Display student submission with grading form, or save grades (POST)."""
    student_assignment = get_object_or_404(
        StudentAssignment.objects.select_related(
            'assignment', 'assignment__class_obj', 'assignment__subject', 'student'
        ),
        pk=pk,
    )

    # Permission check
    if not _teacher_can_grade_submission(request.user, student_assignment):
        raise Http404("You don't have permission to grade this submission.")

    assignment = student_assignment.assignment
    student = student_assignment.student

    # Load questions and student's answers
    questions = list(
        Question.objects.filter(assignment=assignment).order_by('order')
    )
    answers_by_question = {
        a.question_id: a
        for a in Answer.objects.filter(student_assignment=student_assignment)
    }

    # Build grading data structure
    grading_items = []
    for q in questions:
        ans = answers_by_question.get(q.id)
        grading_items.append({
            'question': q,
            'answer': ans,
            'marks_awarded': ans.marks_awarded if ans else None,
            'feedback': ans.feedback if ans else '',
            'student_response': _format_student_response(q, ans),
            'correct_answer': q.correct_answer if q.question_type == Question.TYPE_MCQ else None,
        })

    # Handle POST (save grading)
    if request.method == 'POST':
        return _save_grading(request, student_assignment, grading_items)

    # Calculate current total
    total_marks_awarded = sum(
        item['marks_awarded'] or 0 for item in grading_items
    )

    return render(request, 'teacher/grading/grade.html', {
        'user': request.user,
        'student_assignment': student_assignment,
        'assignment': assignment,
        'student': student,
        'grading_items': grading_items,
        'total_marks_awarded': total_marks_awarded,
        'total_possible': assignment.total_marks,
        'active_page': 'gradebook',
    })


def _format_student_response(question, answer):
    """Format the student's response for display."""
    if not answer:
        return {'type': 'no_answer', 'display': 'No answer submitted'}

    if question.question_type == Question.TYPE_MCQ:
        # Find the option text
        if answer.selected_option_key:
            for opt in question.options:
                if opt.get('key') == answer.selected_option_key:
                    return {
                        'type': 'mcq',
                        'display': f"{answer.selected_option_key}: {opt.get('text', '')}",
                        'is_correct': answer.selected_option_key == question.correct_answer,
                    }
        return {'type': 'mcq', 'display': answer.selected_option_key or 'No selection'}

    elif question.question_type == Question.TYPE_SHORT:
        return {'type': 'short', 'display': answer.answer_text or 'No answer'}

    elif question.question_type == Question.TYPE_ESSAY:
        return {'type': 'essay', 'display': answer.answer_text or 'No answer'}

    elif question.question_type == Question.TYPE_UPLOAD:
        if answer.file:
            return {'type': 'upload', 'display': answer.file.name, 'url': answer.file.url}
        return {'type': 'upload', 'display': 'No file uploaded'}

    return {'type': 'unknown', 'display': 'Unknown response type'}


@transaction.atomic
def _save_grading(request, student_assignment, grading_items):
    """Save the grading marks and feedback, then mark as GRADED."""
    total_marks_awarded = 0
    errors = []

    # Process each question's grading
    for idx, item in enumerate(grading_items):
        question = item['question']
        answer = item['answer']

        # Get marks from form
        marks_key = f'marks_{question.id}'
        feedback_key = f'feedback_{question.id}'

        marks_str = request.POST.get(marks_key, '').strip()
        feedback = request.POST.get(feedback_key, '').strip()

        # Validate marks
        try:
            if marks_str == '':
                marks_awarded = None
            else:
                marks_awarded = int(marks_str)
                if marks_awarded < 0:
                    errors.append(f"Q{idx+1}: Marks cannot be negative")
                    continue
                if marks_awarded > question.marks:
                    errors.append(f"Q{idx+1}: Marks ({marks_awarded}) exceed max ({question.marks})")
                    continue
        except ValueError:
            errors.append(f"Q{idx+1}: Invalid marks value")
            continue

        # Create or update answer record
        if answer:
            if marks_awarded is not None:
                answer.marks_awarded = marks_awarded
            answer.feedback = feedback
            answer.is_correct = (marks_awarded == question.marks) if marks_awarded is not None else None
            answer.save(update_fields=['marks_awarded', 'feedback', 'is_correct', 'updated_at'])
        else:
            # Student didn't answer this question, but teacher can still add feedback
            Answer.objects.create(
                student_assignment=student_assignment,
                question=question,
                marks_awarded=marks_awarded,
                feedback=feedback,
                is_correct=(marks_awarded == question.marks) if marks_awarded is not None else None,
            )

        if marks_awarded is not None:
            total_marks_awarded += marks_awarded

    if errors:
        for err in errors:
            messages.error(request, err)
        return redirect('teacher:grading_view', pk=student_assignment.id)

    # Update StudentAssignment
    student_assignment.score = total_marks_awarded
    student_assignment.max_score = student_assignment.assignment.total_marks
    student_assignment.status = StudentAssignment.STATUS_GRADED
    student_assignment.graded_at = timezone.now()
    student_assignment.save(update_fields=['score', 'max_score', 'status', 'graded_at', 'updated_at'])

    messages.success(
        request,
        f'Successfully graded {student_assignment.student.get_full_name()}: '
        f'{total_marks_awarded}/{student_assignment.max_score} ({student_assignment.score_percent}%)'
    )

    # Redirect back to gradebook
    return redirect('teacher:gradebook')
