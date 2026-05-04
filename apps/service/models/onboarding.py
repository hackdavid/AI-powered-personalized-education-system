"""
OnboardingResult — records the student's answers to the Awakening flow.
Used by the OnboardingRequiredMiddleware (different subagent) to resume
partial progress and by the dashboard to compute calibrated rank.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models.base import TimestampedModel


class OnboardingResult(TimestampedModel):
    STEP_WELCOME = 1
    STEP_IDENTITY = 2
    STEP_LEARNING_STYLE = 3
    STEP_GOAL = 4
    STEP_APTITUDE = 5
    STEP_COMPLETE = 6
    TOTAL_STEPS = 5

    student = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='onboarding',
    )
    current_step = models.PositiveSmallIntegerField(default=STEP_WELCOME)
    step_1_identity = models.JSONField(default=dict, blank=True)
    step_2_learning_style = models.JSONField(default=dict, blank=True)
    step_3_goal = models.JSONField(default=dict, blank=True)
    step_4_aptitude = models.JSONField(default=dict, blank=True)
    calibrated_rank = models.CharField(max_length=1, default='E', blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'Onboarding<{self.student_id} step={self.current_step}>'

    def mark_complete(self):
        self.current_step = self.STEP_COMPLETE
        self.completed_at = timezone.now()
        self.save()
