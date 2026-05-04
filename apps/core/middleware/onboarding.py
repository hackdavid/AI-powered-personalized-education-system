"""OnboardingRequiredMiddleware — forces incomplete students to /student/awakening.

Any authenticated student hitting /student/* or /dashboard/ with
profile.onboarding_complete == False is redirected to the Awakening flow.
Non-students (teacher, school_admin, system_admin, Django superusers)
are never affected.
"""

import logging

from django.http import HttpResponseRedirect
from django.urls import NoReverseMatch, reverse
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class OnboardingRequiredMiddleware(MiddlewareMixin):
    # Paths that must remain reachable for incomplete students.
    ALLOWED_PREFIXES = (
        '/student/awakening',
        '/auth/',
        '/admin/',
        '/health',
        '/api/',
        '/static/',
        '/media/',
        '/student/shell-preview',  # dev preview from Wave 1B
    )

    # Paths gated by this middleware. Everything else passes through.
    GATED_PREFIXES = ('/student/', '/dashboard')

    def process_request(self, request):
        # Anonymous requests are handled by other auth middleware.
        if not request.user.is_authenticated:
            return None

        # Only students are gated.
        if not getattr(request.user, 'is_student', False):
            return None

        path = request.path

        # Allowlist short-circuit.
        for prefix in self.ALLOWED_PREFIXES:
            if path.startswith(prefix):
                return None

        # Only redirect from student-facing routes.
        if not any(path.startswith(p) for p in self.GATED_PREFIXES):
            return None

        # Missing profile (defensive — backfill should have created one).
        try:
            profile = request.user.profile
        except Exception:
            logger.debug('No profile for student %s; redirecting to awakening',
                         request.user.email)
            return self._redirect_to_awakening()

        if not profile.onboarding_complete:
            logger.debug('Student %s onboarding incomplete; walling',
                         request.user.email)
            return self._redirect_to_awakening()

        return None

    def _redirect_to_awakening(self):
        try:
            return HttpResponseRedirect(reverse('student:awakening'))
        except NoReverseMatch:
            # W2B may still be landing; fall back to the hardcoded path.
            return HttpResponseRedirect('/student/awakening/')
