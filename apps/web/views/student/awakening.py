"""Awakening (onboarding) flow — 5 gated steps that every student must complete.

Partial progress is persisted in OnboardingResult.current_step so a closed
tab resumes at the same step. Users cannot skip ahead; early-step URLs
redirect back to the current step.
"""

import logging

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from apps.core.decorators import role_required
from apps.service.models import OnboardingResult
from apps.service.services.onboarding import (
    apply_calibration, complete_awakening,
    get_aptitude_questions, grade_aptitude_responses,
)

logger = logging.getLogger(__name__)


# Map a step number to its URL name — used for "redirect back to current step"
STEP_URL_NAME = {
    OnboardingResult.STEP_WELCOME: 'student:awakening',
    OnboardingResult.STEP_IDENTITY: 'student:awakening_identity',
    OnboardingResult.STEP_LEARNING_STYLE: 'student:awakening_learning_style',
    OnboardingResult.STEP_GOAL: 'student:awakening_goal',
    OnboardingResult.STEP_APTITUDE: 'student:awakening_aptitude',
    OnboardingResult.STEP_COMPLETE: 'student:awakening_complete',
}


HUNTER_TITLES = [
    {'key': 'scholar', 'name': 'Scholar',
     'tag': 'Knowledge seeker', 'desc': 'Depth over speed. Loves structure.'},
    {'key': 'tactician', 'name': 'Tactician',
     'tag': 'Strategic mind', 'desc': 'Plans, iterates, optimises.'},
    {'key': 'explorer', 'name': 'Explorer',
     'tag': 'Curiosity first', 'desc': 'Follows interesting tangents.'},
    {'key': 'strategist', 'name': 'Strategist',
     'tag': 'Big picture', 'desc': 'Connects dots between subjects.'},
]

INTEREST_TAGS = ['Math', 'Science', 'Languages', 'History', 'Coding', 'Arts']

LEARNING_STYLE_QUESTIONS = [
    {
        'key': 'q1',
        'question': 'How do you best understand a new concept?',
        'options': [
            ('v', 'See a diagram or chart'),
            ('a', 'Hear someone explain it'),
            ('r', 'Read about it in detail'),
            ('k', 'Try it out yourself'),
        ],
    },
    {
        'key': 'q2',
        'question': 'When studying for a test, you prefer to...',
        'options': [
            ('v', 'Watch worked examples on video'),
            ('a', 'Discuss with a classmate'),
            ('r', 'Re-read your notes'),
            ('k', 'Solve practice problems'),
        ],
    },
    {
        'key': 'q3',
        'question': 'A new topic clicks best for you when you...',
        'options': [
            ('v', 'See it as a visual pattern'),
            ('a', 'Hear a clear explanation'),
            ('r', 'Read a well-structured article'),
            ('k', 'Apply it in an example'),
        ],
    },
    {
        'key': 'q4',
        'question': 'You remember things best through...',
        'options': [
            ('v', 'Images and diagrams'),
            ('a', 'Spoken information'),
            ('r', 'Written notes'),
            ('k', 'Hands-on doing'),
        ],
    },
]

GOAL_TEMPLATES = [
    'Improve in my weakest subject',
    'Pass this term confidently',
    'Top of the class',
    'Master one specific topic',
]


def _get_result(user) -> OnboardingResult:
    result, _ = OnboardingResult.objects.get_or_create(student=user)
    return result


def _ensure_on_step(result: OnboardingResult, required_step: int):
    """If user is trying to access a step ahead of their progress, return
    a redirect to the current step. Otherwise return None."""
    if result.current_step < required_step:
        target = STEP_URL_NAME.get(result.current_step, 'student:awakening')
        return redirect(target)
    return None


@login_required
@role_required(['student'])
def welcome_view(request):
    result = _get_result(request.user)
    if result.current_step > OnboardingResult.STEP_WELCOME and request.method == 'GET':
        # If user already past step 1, bounce them to current step
        if result.current_step >= OnboardingResult.STEP_COMPLETE:
            return redirect('student:awakening_complete')
        # For steps 2..5, let them see welcome (soft; optional) but link forward.
    return render(request, 'student/awakening/welcome.html', {
        'current_step': 1,
        'total_steps': 5,
        'active_page': 'awakening',
    })


@login_required
@role_required(['student'])
def identity_view(request):
    result = _get_result(request.user)
    redirect_response = _ensure_on_step(result, OnboardingResult.STEP_WELCOME)
    if redirect_response:
        return redirect_response

    if request.method == 'POST':
        hunter_title = request.POST.get('hunter_title', '').strip()
        interest_tags = request.POST.getlist('interest_tags')
        if not hunter_title:
            return render(request, 'student/awakening/identity.html', {
                'current_step': 1, 'total_steps': 5,
                'titles': HUNTER_TITLES, 'interest_tags': INTEREST_TAGS,
                'selected_title': '', 'selected_tags': interest_tags,
                'error': 'Choose a Hunter Title to continue.',
                'active_page': 'awakening',
            })
        result.step_1_identity = {
            'hunter_title': hunter_title,
            'interest_tags': interest_tags[:5],
        }
        result.current_step = OnboardingResult.STEP_LEARNING_STYLE
        result.save()
        return redirect('student:awakening_learning_style')

    prior = result.step_1_identity or {}
    return render(request, 'student/awakening/identity.html', {
        'current_step': 1, 'total_steps': 5,
        'titles': HUNTER_TITLES,
        'interest_tags': INTEREST_TAGS,
        'selected_title': prior.get('hunter_title', ''),
        'selected_tags': prior.get('interest_tags', []),
        'active_page': 'awakening',
    })


@login_required
@role_required(['student'])
def learning_style_view(request):
    result = _get_result(request.user)
    redirect_response = _ensure_on_step(result, OnboardingResult.STEP_LEARNING_STYLE)
    if redirect_response:
        return redirect_response

    if request.method == 'POST':
        answers = {}
        scores = {'v': 0, 'a': 0, 'r': 0, 'k': 0}
        for q in LEARNING_STYLE_QUESTIONS:
            val = request.POST.get(q['key'], '').strip()
            if val in scores:
                answers[q['key']] = val
                scores[val] += 1
        if len(answers) < len(LEARNING_STYLE_QUESTIONS):
            return render(request, 'student/awakening/learning_style.html', {
                'current_step': 2, 'total_steps': 5,
                'questions': LEARNING_STYLE_QUESTIONS,
                'error': 'Please answer all four questions.',
                'active_page': 'awakening',
            })
        dominant = max(scores, key=scores.get)
        result.step_2_learning_style = {
            'answers': answers, 'scores': scores, 'dominant': dominant,
        }
        result.current_step = OnboardingResult.STEP_GOAL
        result.save()
        return redirect('student:awakening_goal')

    return render(request, 'student/awakening/learning_style.html', {
        'current_step': 2, 'total_steps': 5,
        'questions': LEARNING_STYLE_QUESTIONS,
        'active_page': 'awakening',
    })


@login_required
@role_required(['student'])
def goal_view(request):
    result = _get_result(request.user)
    redirect_response = _ensure_on_step(result, OnboardingResult.STEP_GOAL)
    if redirect_response:
        return redirect_response

    if request.method == 'POST':
        template = request.POST.get('goal_template', '').strip()
        title = request.POST.get('goal_title', '').strip()[:200]
        description = request.POST.get('goal_description', '').strip()[:2000]
        if not title:
            return render(request, 'student/awakening/goal.html', {
                'current_step': 3, 'total_steps': 5,
                'templates': GOAL_TEMPLATES,
                'error': 'Give your goal a name.',
                'active_page': 'awakening',
            })
        result.step_3_goal = {
            'template': template, 'title': title, 'description': description,
        }
        result.current_step = OnboardingResult.STEP_APTITUDE
        result.save()
        return redirect('student:awakening_aptitude')

    prior = result.step_3_goal or {}
    return render(request, 'student/awakening/goal.html', {
        'current_step': 3, 'total_steps': 5,
        'templates': GOAL_TEMPLATES,
        'selected_template': prior.get('template', ''),
        'prior_title': prior.get('title', ''),
        'prior_description': prior.get('description', ''),
        'active_page': 'awakening',
    })


@login_required
@role_required(['student'])
def aptitude_view(request):
    result = _get_result(request.user)
    redirect_response = _ensure_on_step(result, OnboardingResult.STEP_APTITUDE)
    if redirect_response:
        return redirect_response

    state = result.step_4_aptitude or {}
    questions = state.get('questions')
    if not questions:
        questions = get_aptitude_questions(request.user, num_questions=5)
        state = {'questions': questions, 'current_index': 0, 'responses': []}
        result.step_4_aptitude = state
        result.save(update_fields=['step_4_aptitude', 'updated_at'])

    current_index = state.get('current_index', 0)

    if request.method == 'POST':
        selected = request.POST.get('selected', '').strip()
        if 0 <= current_index < len(questions):
            state['responses'].append({
                'id': questions[current_index]['id'],
                'selected': selected,
            })
            state['current_index'] = current_index + 1
            result.step_4_aptitude = state
            result.save(update_fields=['step_4_aptitude', 'updated_at'])

        if state['current_index'] >= len(questions):
            tally = grade_aptitude_responses(questions, state['responses'])
            rank = apply_calibration(request.user, tally)
            result.calibrated_rank = rank
            result.current_step = OnboardingResult.STEP_COMPLETE
            result.save()
            return redirect('student:awakening_complete')

        return redirect('student:awakening_aptitude')

    if not questions:
        # No curriculum → skip probe, move on with default rank
        result.calibrated_rank = 'E'
        result.current_step = OnboardingResult.STEP_COMPLETE
        result.save()
        return redirect('student:awakening_complete')

    question = questions[current_index] if current_index < len(questions) else None
    return render(request, 'student/awakening/aptitude.html', {
        'current_step': 4, 'total_steps': 5,
        'question': question,
        'question_number': current_index + 1,
        'total_questions': len(questions),
        'active_page': 'awakening',
    })


@login_required
@role_required(['student'])
def complete_view(request):
    result = _get_result(request.user)
    if result.current_step < OnboardingResult.STEP_COMPLETE:
        # Not ready yet
        target = STEP_URL_NAME.get(result.current_step, 'student:awakening')
        return redirect(target)

    profile = complete_awakening(request.user)
    mastery_rows = []
    # Join mastery with subject names for nicer display
    from apps.service.models import Subject
    if profile.mastery_per_subject:
        subject_map = {str(s.id): s.name for s in Subject.objects.filter(
            tenant=request.user.tenant,
        )}
        for sid, pct in profile.mastery_per_subject.items():
            mastery_rows.append({
                'subject': subject_map.get(str(sid), f'Subject {sid}'),
                'pct': pct,
            })
        mastery_rows.sort(key=lambda r: -r['pct'])

    return render(request, 'student/awakening/complete.html', {
        'current_step': 5,
        'total_steps': 5,
        'profile': profile,
        'rank': profile.rank,
        'hunter_title': profile.hunter_title,
        'mastery_rows': mastery_rows,
        'active_page': 'awakening',
    })
