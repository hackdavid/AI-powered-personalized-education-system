"""
Seed Phase B demo data (quests, hunts, XP, daily quests, mission briefs).

Produces realistic gamification state so the redesigned student UI has
something visually meaningful to render:

    * Every active student ends up enrolled in a Class (Enrollment).
    * A handful of "demo" students are fully onboarded, carry real
      mastery/streak state, and have starting XP in the ledger.
    * Each Class has a couple of published Quests (Assignments) with
      real Questions attached.
    * Each demo student has one active Hunt (Goal) with decomposed
      Tasks and at least one completed Task so progress is non-zero.
    * Today's Mission Brief is regenerated so dashboards have items.

Operates PER TENANT. Idempotent across reruns.

Examples
--------
    # All active tenants, defaults
    python manage.py seed_phase_b_demo

    # Dry run first
    python manage.py seed_phase_b_demo --dry-run

    # One tenant, reset its Phase B data, attempt real LLM calls
    python manage.py seed_phase_b_demo --tenant springfield --reset --use-llm

    # Repeatable --tenant flag
    python manage.py seed_phase_b_demo --tenant springfield --tenant riverside
"""

from __future__ import annotations

import logging
import os
import random
from datetime import timedelta
from typing import Dict, List, Optional

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, Tenant, User
from apps.service.models import (
    Assignment,
    Class,
    ClassSubject,
    ContentNode,
    DailyQuest,
    Enrollment,
    Goal,
    MissionBrief,
    OnboardingResult,
    Question,
    StudentAssignment,
    StudentProfile,
    Subject,
    Task,
    XPLedger,
)
from apps.service.services.hunts import decompose_goal
from apps.service.services.missions import ensure_todays_brief
from apps.service.services.xp import award_xp


logger = logging.getLogger(__name__)


HUNTER_TITLES = ['Scholar', 'Tactician', 'Explorer', 'Strategist']
INTEREST_TAG_POOL = ['Math', 'Science', 'Languages', 'History', 'Arts']
LEARNING_STYLE_DEFAULT = {
    'dominant': 'v',
    'scores': {'v': 3, 'a': 1, 'r': 2, 'k': 1},
    'answers': {'q1': 'v', 'q2': 'r', 'q3': 'v', 'q4': 'k'},
}

# Aggregate totals reported at the end of the whole run.
_EMPTY_TOTALS = {
    'tenants_processed': 0,
    'enrollments_created': 0,
    'demo_students_onboarded': 0,
    'assignments_created': 0,
    'questions_created': 0,
    'hunts_created': 0,
    'hunt_tasks_created': 0,
    'hunt_tasks_completed': 0,
    'xp_ledger_rows': 0,
    'mission_briefs_generated': 0,
    'reset_rows_deleted': 0,
}


class Command(BaseCommand):
    help = 'Seed Phase B demo data (quests, hunts, XP, daily quests, mission briefs).'

    # ------------------------------------------------------------------
    # argparse
    # ------------------------------------------------------------------

    def add_arguments(self, parser):
        parser.add_argument(
            '--tenant',
            action='append',
            default=None,
            metavar='SLUG',
            help='Tenant slug to seed. Repeatable. Default: every active tenant.',
        )
        parser.add_argument(
            '--demo-students',
            type=int,
            default=2,
            help='How many students per tenant to mark as fully onboarded with progress.',
        )
        parser.add_argument(
            '--quests-per-class',
            type=int,
            default=2,
            help='Assignments created per class-subject pair. Default: 2.',
        )
        parser.add_argument(
            '--use-llm',
            action='store_true',
            help='Attempt real LLM calls for question generation + hunt decomposition.',
        )
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Delete existing Phase B demo data for the tenant before reseeding.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print what would happen but do not commit changes.',
        )

    # ------------------------------------------------------------------
    # entrypoint
    # ------------------------------------------------------------------

    def handle(self, *args, **opts):
        dry_run = opts['dry_run']
        use_llm = opts['use_llm']

        if use_llm and not getattr(settings, 'OPENAI_API_KEY', ''):
            self.stdout.write(self.style.WARNING(
                '[warn] --use-llm was passed but OPENAI_API_KEY is empty; '
                'services will fall back to stub behaviour.'
            ))

        tenants = self._resolve_tenants(opts['tenant'])
        if not tenants:
            raise CommandError(
                'No active tenants match the --tenant filter. '
                'Run `python manage.py seed_synthetic_data` first.'
            )

        totals = dict(_EMPTY_TOTALS)
        totals['tenants_processed'] = len(tenants)

        for tenant in tenants:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\n=== Seeding Phase B demo: {tenant.slug} ==="
            ))
            try:
                per_tenant = self._seed_one_tenant(tenant, opts)
            except Exception as exc:
                # transaction.atomic already rolled this tenant back; surface the error.
                logger.exception('Phase B seed failed for tenant %s', tenant.slug)
                self.stdout.write(self.style.ERROR(
                    f'[{tenant.slug}] aborted: {exc}'
                ))
                continue
            for k, v in per_tenant.items():
                totals[k] = totals.get(k, 0) + v

        self._print_summary(totals, dry_run=dry_run)

    # ------------------------------------------------------------------
    # per-tenant pipeline
    # ------------------------------------------------------------------

    def _seed_one_tenant(self, tenant: Tenant, opts: dict) -> Dict[str, int]:
        dry_run = opts['dry_run']

        per_tenant = {
            'enrollments_created': 0,
            'demo_students_onboarded': 0,
            'assignments_created': 0,
            'questions_created': 0,
            'hunts_created': 0,
            'hunt_tasks_created': 0,
            'hunt_tasks_completed': 0,
            'xp_ledger_rows': 0,
            'mission_briefs_generated': 0,
            'reset_rows_deleted': 0,
        }

        # ---------------- optional reset (own atomic block) ----------------
        if opts['reset']:
            if dry_run:
                would = self._count_reset_targets(tenant)
                self._log(tenant, f'[dry-run] Reset would delete {would} Phase B rows.')
                per_tenant['reset_rows_deleted'] = would
            else:
                with transaction.atomic():
                    deleted = self._reset_phase_b_data(tenant)
                self._log(tenant, f'Reset: deleted {deleted} Phase B rows.')
                per_tenant['reset_rows_deleted'] = deleted

        # ---------------- main seeding (one atomic block per tenant) ------
        if dry_run:
            plan = self._plan_tenant(tenant, opts)
            self._log(tenant, '[dry-run] ' + ', '.join(f'{k}={v}' for k, v in plan.items()))
            per_tenant.update(plan)
            return per_tenant

        with transaction.atomic():
            # Step 1: Enrollments
            count = self._backfill_enrollments(tenant)
            per_tenant['enrollments_created'] = count
            self._log(tenant, f'Enrollments created: {count}')

            # Step 2: demo students
            demo_students = self._pick_demo_students(tenant, opts['demo_students'])
            onboarded = self._onboard_demo_students(tenant, demo_students)
            per_tenant['demo_students_onboarded'] = onboarded
            self._log(tenant, f'Demo students onboarded: {onboarded}')

            # Step 3: starting XP for demo students
            xp_rows = self._seed_starting_xp(demo_students)
            per_tenant['xp_ledger_rows'] += xp_rows
            self._log(tenant, f'Starting XP ledger rows: {xp_rows}')

            # Step 4: Assignments + Questions per ClassSubject
            a_count, q_count = self._seed_assignments(
                tenant,
                quests_per_class=opts['quests_per_class'],
                use_llm=opts['use_llm'],
            )
            per_tenant['assignments_created'] = a_count
            per_tenant['questions_created'] = q_count
            self._log(tenant, f'Assignments created: {a_count} (questions: {q_count})')

            # Step 5: Hunts per demo student
            hunts, tasks, completed = self._seed_hunts(demo_students, use_llm=opts['use_llm'])
            per_tenant['hunts_created'] = hunts
            per_tenant['hunt_tasks_created'] = tasks
            per_tenant['hunt_tasks_completed'] = completed
            self._log(tenant, f'Hunts created: {hunts} (tasks: {tasks}, completed: {completed})')

            # Step 6: today's Mission Brief
            briefs = self._seed_mission_briefs(demo_students)
            per_tenant['mission_briefs_generated'] = briefs
            self._log(tenant, f'Mission briefs generated: {briefs}')

        return per_tenant

    # ------------------------------------------------------------------
    # helpers - tenant resolution
    # ------------------------------------------------------------------

    def _resolve_tenants(self, slugs: Optional[List[str]]) -> List[Tenant]:
        qs = Tenant.objects.filter(is_active=True)
        if slugs:
            qs = qs.filter(slug__in=slugs)
        return list(qs.order_by('slug'))

    # ------------------------------------------------------------------
    # helpers - reset
    # ------------------------------------------------------------------

    def _count_reset_targets(self, tenant: Tenant) -> int:
        student_ids = list(
            User.objects.filter(
                tenant=tenant, role__name=Role.STUDENT,
            ).values_list('id', flat=True)
        )
        if not student_ids:
            return 0
        today = timezone.localdate()
        return sum([
            Assignment.objects.filter(tenant=tenant).count(),
            Goal.objects.filter(student_id__in=student_ids).count(),
            DailyQuest.objects.filter(student_id__in=student_ids).count(),
            XPLedger.objects.filter(student_id__in=student_ids).count(),
            MissionBrief.objects.filter(student_id__in=student_ids, date=today).count(),
        ])

    def _reset_phase_b_data(self, tenant: Tenant) -> int:
        """Delete Phase B demo rows scoped to this tenant's students.

        StudentAssignment/Answer, Task cascade from their parents.
        Also clears today's MissionBriefs so they regenerate with fresh
        items (otherwise `ensure_todays_brief` would see an existing brief
        with stale items pointing at deleted Assignments).
        """
        student_ids = list(
            User.objects.filter(
                tenant=tenant, role__name=Role.STUDENT,
            ).values_list('id', flat=True)
        )
        deleted = 0
        # Assignments scoped by tenant (cascade kills Questions / StudentAssignments / Answers).
        a_count, _ = Assignment.objects.filter(tenant=tenant).delete()
        deleted += a_count
        if student_ids:
            g_count, _ = Goal.objects.filter(student_id__in=student_ids).delete()
            deleted += g_count
            d_count, _ = DailyQuest.objects.filter(student_id__in=student_ids).delete()
            deleted += d_count
            x_count, _ = XPLedger.objects.filter(student_id__in=student_ids).delete()
            deleted += x_count
            # Today's MissionBriefs — their items reference now-deleted
            # Assignments, so regenerate them from scratch. ensure_todays_brief
            # will recreate them on the next run because the brief-items set
            # will be empty.
            today = timezone.localdate()
            b_count, _ = MissionBrief.objects.filter(
                student_id__in=student_ids, date=today,
            ).delete()
            deleted += b_count
            # Reset StudentProfile counters so award_xp starts fresh.
            StudentProfile.objects.filter(student_id__in=student_ids).update(
                total_xp=0, level=1, rank=StudentProfile.RANK_E,
                daily_xp_earned=0, daily_xp_reset_date=None,
            )
        return deleted

    # ------------------------------------------------------------------
    # helpers - dry-run planner
    # ------------------------------------------------------------------

    def _plan_tenant(self, tenant: Tenant, opts: dict) -> Dict[str, int]:
        """Estimate the counts a real run would create. No DB writes."""
        # Enrollments: missing for every active student.
        students = list(User.objects.filter(
            tenant=tenant, role__name=Role.STUDENT, is_active=True,
        ))
        enrolled_student_ids = set(
            Enrollment.objects.filter(
                class_obj__tenant=tenant, student__in=students, is_active=True,
            ).values_list('student_id', flat=True)
        )
        enrollments = sum(
            1 for s in students
            if s.id not in enrolled_student_ids
            and Class.objects.filter(
                tenant=tenant, grade_level=s.grade_level, is_active=True,
            ).exists()
        )

        demo_students = min(opts['demo_students'], len(students))

        # Assignments: one per (class, subject-pair, quest-index) that doesn't exist yet.
        assignments_planned = 0
        for cls in Class.objects.filter(tenant=tenant, is_active=True):
            cls_subjects = list(cls.class_subjects.filter(is_active=True))[:opts['quests_per_class']]
            for i, cs in enumerate(cls_subjects):
                title = self._assignment_title(cs.subject, i)
                exists = Assignment.objects.filter(
                    class_obj=cls, subject=cs.subject, title=title,
                ).exists()
                if not exists:
                    assignments_planned += 1

        questions_planned = assignments_planned * 5
        hunts_planned = demo_students  # one hunt per demo student
        tasks_planned = hunts_planned * 6  # stub fallback

        return {
            'enrollments_created': enrollments,
            'demo_students_onboarded': demo_students,
            'assignments_created': assignments_planned,
            'questions_created': questions_planned,
            'hunts_created': hunts_planned,
            'hunt_tasks_created': tasks_planned,
            'hunt_tasks_completed': hunts_planned,  # at least 1 per hunt
            'xp_ledger_rows': demo_students * 3,
            'mission_briefs_generated': demo_students,
        }

    # ------------------------------------------------------------------
    # step 1: enrollments
    # ------------------------------------------------------------------

    def _backfill_enrollments(self, tenant: Tenant) -> int:
        """Assign every active student a Class within their grade. Round-robin
        across sections so cohorts spread out.
        """
        students = list(User.objects.filter(
            tenant=tenant, role__name=Role.STUDENT, is_active=True,
        ).order_by('email'))
        if not students:
            return 0

        # Pre-group classes by grade.
        classes_by_grade: Dict[int, List[Class]] = {}
        for cls in Class.objects.filter(tenant=tenant, is_active=True).order_by('grade_level', 'section'):
            classes_by_grade.setdefault(cls.grade_level, []).append(cls)

        # Counter per grade so we round-robin across sections within a grade.
        counter: Dict[int, int] = {g: 0 for g in classes_by_grade}

        created = 0
        for s in students:
            if s.grade_level is None:
                continue
            classes = classes_by_grade.get(s.grade_level)
            if not classes:
                continue
            idx = counter[s.grade_level] % len(classes)
            counter[s.grade_level] += 1
            cls = classes[idx]
            _, was_created = Enrollment.objects.get_or_create(
                class_obj=cls, student=s,
                defaults={'is_active': True},
            )
            if was_created:
                created += 1
        return created

    # ------------------------------------------------------------------
    # step 2: demo student onboarding
    # ------------------------------------------------------------------

    def _pick_demo_students(self, tenant: Tenant, count: int) -> List[User]:
        return list(
            User.objects.filter(
                tenant=tenant, role__name=Role.STUDENT, is_active=True,
            ).order_by('email')[:count]
        )

    def _onboard_demo_students(self, tenant: Tenant, students: List[User]) -> int:
        subjects = list(Subject.objects.filter(tenant=tenant, is_active=True))
        onboarded = 0

        for idx, student in enumerate(students):
            rng = random.Random(student.id)

            mastery = {str(s.id): rng.randint(30, 85) for s in subjects}
            streak = rng.randint(1, 12)
            title = HUNTER_TITLES[idx % len(HUNTER_TITLES)]
            interests = rng.sample(INTEREST_TAG_POOL, k=min(3, len(INTEREST_TAG_POOL)))

            profile, _ = StudentProfile.objects.get_or_create(student=student)
            profile.hunter_title = title
            profile.interest_tags = interests
            profile.learning_style = dict(LEARNING_STYLE_DEFAULT)
            profile.mastery_per_subject = mastery
            profile.streak_days = streak
            profile.onboarding_complete = True
            if not profile.last_active_date:
                profile.last_active_date = timezone.localdate()
            profile.save()

            # OnboardingResult row — mark fully complete with calibrated D rank
            now = timezone.now()
            OnboardingResult.objects.update_or_create(
                student=student,
                defaults={
                    'current_step': OnboardingResult.STEP_COMPLETE,
                    'completed_at': now,
                    'calibrated_rank': StudentProfile.RANK_D,
                    'step_1_identity': {'hunter_title': title, 'interests': interests},
                    'step_2_learning_style': dict(LEARNING_STYLE_DEFAULT),
                    'step_3_goal': {'label': 'Demo goal', 'target_days': 14},
                    'step_4_aptitude': {'score': rng.randint(50, 90)},
                },
            )
            onboarded += 1
        return onboarded

    # ------------------------------------------------------------------
    # step 3: starting XP
    # ------------------------------------------------------------------

    def _seed_starting_xp(self, students: List[User]) -> int:
        """Award 200-500 XP per demo student, split over a few ledger rows.

        Skips students who already have ledger rows (idempotency).
        """
        rows = 0
        for student in students:
            if XPLedger.objects.filter(student=student).exists():
                continue
            rng = random.Random(student.id * 7919)
            # Three natural-looking gains totalling 200-500.
            total = rng.randint(200, 500)
            # Split: awakening ~25%, quest ~45%, hunt_task ~30%
            awakening = max(25, int(total * 0.25))
            quest = max(25, int(total * 0.45))
            hunt = max(25, total - awakening - quest)

            award_xp(
                student,
                source=XPLedger.SOURCE_AWAKENING,
                amount=awakening,
                description='Awakening complete',
                ignore_cap=True,
            )
            award_xp(
                student,
                source=XPLedger.SOURCE_QUEST,
                amount=quest,
                description='Demo Quest A',
                ignore_cap=True,
            )
            award_xp(
                student,
                source=XPLedger.SOURCE_HUNT_TASK,
                amount=hunt,
                description='Seeded hunt progress',
                ignore_cap=True,
            )
            rows += 3
        return rows

    # ------------------------------------------------------------------
    # step 4: assignments + questions
    # ------------------------------------------------------------------

    def _assignment_title(self, subject: Subject, index: int) -> str:
        """Stable title used as the idempotency key for an Assignment.

        Stored shape: `"{subject.name}: {topic_title or default}"`. The
        index is woven into the topic title at creation time so the first
        quest for a subject isn't clobbered by the second.
        """
        # A deterministic placeholder; the real topic is picked at create time
        # (we pass the actual title through here to ensure uniqueness check).
        return subject.name  # this is replaced by the caller with the real title

    def _pick_topic_node(
        self, tenant: Tenant, subject: Subject, index: int,
    ) -> tuple[str, Optional[ContentNode]]:
        """Pick a topic ContentNode for the subject. Returns (title, node).

        Prefers leaf-type nodes that have actual `content` text — they
        contain richer curriculum grounding than chapter/section titles.
        Falls back to any topic node, then to 'Practice Quest'.
        """
        # Priority 1: non-empty topic/section/definition/summary nodes
        primary = list(
            ContentNode.objects.filter(
                tenant=tenant, subject=subject,
                node_type__in=['topic', 'section', 'definition', 'summary'],
            )
            .exclude(content_plain='')
            .order_by('id')
        )
        if primary:
            node = primary[index % len(primary)]
            return node.title, node

        # Priority 2: any topic-like node (even without content_plain)
        any_topic = list(
            ContentNode.objects.filter(
                tenant=tenant, subject=subject,
                node_type__in=['topic', 'section'],
            ).order_by('id')
        )
        if any_topic:
            node = any_topic[index % len(any_topic)]
            return node.title, node

        return 'Practice Quest', None

    def _school_admin_for(self, tenant: Tenant) -> Optional[User]:
        return User.objects.filter(
            tenant=tenant, role__name=Role.SCHOOL_ADMIN,
        ).order_by('id').first()

    def _seed_assignments(
        self,
        tenant: Tenant,
        quests_per_class: int,
        use_llm: bool,
    ) -> tuple[int, int]:
        admin_fallback = self._school_admin_for(tenant)
        created_assignments = 0
        created_questions = 0

        classes = list(Class.objects.filter(tenant=tenant, is_active=True).order_by('id'))
        now = timezone.now()

        for cls in classes:
            cls_subjects = list(
                cls.class_subjects.filter(is_active=True).select_related('subject', 'teacher')
            )[:quests_per_class]

            for i, cs in enumerate(cls_subjects):
                subject = cs.subject
                topic_title, topic_node = self._pick_topic_node(tenant, subject, i)
                title = f'{subject.name}: {topic_title}'

                # Idempotency — skip if an Assignment with this triple exists.
                if Assignment.objects.filter(
                    class_obj=cls, subject=subject, title=title,
                ).exists():
                    continue

                # Due date: one assignment per class is urgent (<24h); others 2-7 days.
                if i == 0:
                    due = now + timedelta(hours=18)
                else:
                    rng = random.Random(f'{cls.id}:{subject.id}:{i}')
                    due = now + timedelta(days=rng.randint(2, 7))

                creator = cs.teacher or admin_fallback

                assignment = Assignment.objects.create(
                    tenant=tenant,
                    created_by=creator,
                    updated_by=creator,
                    title=title,
                    description=(
                        f'Auto-generated practice quest on "{topic_title}" '
                        f'for {cls.name}.'
                    ),
                    class_obj=cls,
                    subject=subject,
                    due_date=due,
                    total_marks=10,
                    difficulty=3,
                    reward_xp=0,  # auto-derives to 150 via Assignment.save()
                    status=Assignment.STATUS_PUBLISHED,
                    published_at=now,
                )
                created_assignments += 1

                questions = self._generate_questions(
                    topic_title=topic_title,
                    subject=subject,
                    topic_node=topic_node,
                    grade_level=cls.grade_level,
                    use_llm=use_llm,
                )
                for order, q_spec in enumerate(questions):
                    Question.objects.create(
                        assignment=assignment,
                        order=order,
                        question_type=Question.TYPE_MCQ,
                        question_text=q_spec['question_text'],
                        options=q_spec['options'],
                        correct_answer=q_spec['correct_answer'],
                        explanation=q_spec.get('explanation', ''),
                        marks=2,
                    )
                    created_questions += 1

        return created_assignments, created_questions

    def _generate_questions(
        self,
        topic_title: str,
        subject: Subject,
        topic_node: Optional[ContentNode],
        grade_level: Optional[int],
        use_llm: bool,
    ) -> List[dict]:
        """Return a list of question-spec dicts with {question_text, options, correct_answer}.

        LLM path: grounds each question in the ContentNode's curriculum text
        so questions test actual curriculum concepts, not general knowledge.
        Stub path: returns generic distractors per Q.
        """
        if use_llm and getattr(settings, 'OPENAI_API_KEY', ''):
            try:
                from apps.service.services.assessments.question_generator import QuestionGenerator

                content_context = ''
                if topic_node is not None:
                    content_context = (topic_node.content_plain
                                       or topic_node.content
                                       or '').strip()

                raw = QuestionGenerator().generate_questions(
                    topic=topic_title,
                    difficulty='medium',
                    count=5,
                    question_type='mcq',
                    subject_context=subject.name,
                    content_context=content_context,
                    grade_level=grade_level,
                )
                out: List[dict] = []
                for item in raw[:5]:
                    options_list = item.get('options') or []
                    # LLM returns ['A) foo', 'B) bar', ...]; normalize to {key, text} shape.
                    norm_options: List[dict] = []
                    correct_key = 'A'
                    raw_correct = str(item.get('correct_answer', '')).strip()
                    for idx, opt in enumerate(options_list[:4]):
                        key = chr(ord('A') + idx)
                        text = str(opt)
                        # Strip leading "A) " style prefix if present.
                        if len(text) >= 3 and text[1] == ')' and text[0].isalpha():
                            text = text[2:].strip()
                        norm_options.append({'key': key, 'text': text})
                        if raw_correct and (raw_correct.startswith(key) or raw_correct == text):
                            correct_key = key
                    if len(norm_options) < 4:
                        # Pad with stubs so the question is valid.
                        for pad_idx in range(len(norm_options), 4):
                            norm_options.append({
                                'key': chr(ord('A') + pad_idx),
                                'text': f'Distractor {pad_idx + 1}',
                            })
                    out.append({
                        'question_text': str(item.get('question', f'Question on {topic_title}'))[:2000],
                        'options': norm_options,
                        'correct_answer': correct_key,
                        'explanation': str(item.get('explanation', ''))[:500],
                    })
                if len(out) == 5:
                    return out
                # LLM returned fewer than 5 items -> pad with stubs.
                out.extend(self._canned_questions(topic_title, start=len(out), needed=5 - len(out)))
                return out
            except Exception as exc:
                logger.warning('LLM question generation failed: %s - falling back to stub', exc)

        return self._canned_questions(topic_title)

    def _canned_questions(self, topic_title: str, start: int = 0, needed: int = 5) -> List[dict]:
        """Deterministic MCQs keyed off the topic title."""
        prompts = [
            f'What is the main concept introduced in "{topic_title}"?',
            f'Which of the following best describes "{topic_title}"?',
            f'A student studying "{topic_title}" should first focus on:',
            f'Which example most clearly illustrates "{topic_title}"?',
            f'The key takeaway from "{topic_title}" is:',
        ]
        out: List[dict] = []
        for i in range(start, start + needed):
            prompt = prompts[i % len(prompts)]
            options = [
                {'key': 'A', 'text': f'The core idea behind {topic_title}'},
                {'key': 'B', 'text': 'An unrelated concept from another chapter'},
                {'key': 'C', 'text': 'A prerequisite from a previous grade'},
                {'key': 'D', 'text': 'None of the above'},
            ]
            out.append({
                'question_text': prompt,
                'options': options,
                'correct_answer': 'A',
                'explanation': f'The correct choice captures the central idea of {topic_title}.',
            })
        return out

    # ------------------------------------------------------------------
    # step 5: hunts
    # ------------------------------------------------------------------

    def _seed_hunts(
        self,
        students: List[User],
        use_llm: bool,
    ) -> tuple[int, int, int]:
        """Create one active Hunt per demo student. Decompose into Tasks via
        the real service (LLM with stub fallback). Mark 1-2 tasks complete so
        progress_pct > 0.
        """
        hunts_created = 0
        tasks_created = 0
        tasks_completed = 0

        today = timezone.localdate()

        for student in students:
            # Pick a subject the student is enrolled in (first one by id).
            enrollments = list(
                Enrollment.objects.filter(
                    student=student, is_active=True,
                ).select_related('class_obj')
            )
            subject: Optional[Subject] = None
            if enrollments:
                rng = random.Random(student.id)
                enrollment = rng.choice(enrollments)
                class_subjects = list(enrollment.class_obj.class_subjects.filter(is_active=True))
                if class_subjects:
                    subject = rng.choice(class_subjects).subject
            if subject is None:
                subject = Subject.objects.filter(tenant=student.tenant).first()
            if subject is None:
                continue  # no subjects at all for this tenant — skip hunt

            title = f'Master {subject.name}'

            # Idempotency: skip if this student already has a Hunt with this title.
            goal = Goal.objects.filter(student=student, title=title).first()
            if goal is None:
                goal = Goal.objects.create(
                    student=student,
                    title=title,
                    description=(
                        f'A 2-week study plan to bring your {subject.name} mastery '
                        f'above the current baseline.'
                    ),
                    subject=subject,
                    target_date=today + timedelta(days=14),
                    status=Goal.STATUS_ACTIVE,
                )
                hunts_created += 1

            existing_tasks = list(goal.tasks.all())
            if not existing_tasks:
                # decompose_goal will LLM-or-stub depending on config.
                tasks = decompose_goal(goal)
                tasks_created += len(tasks)
            else:
                tasks = existing_tasks

            # Mark 1-2 tasks complete so progress_pct > 0.
            rng = random.Random(student.id * 31)
            to_complete = rng.choice([1, 2])
            for task in tasks[:to_complete]:
                if not task.is_completed:
                    task.mark_completed()
                    tasks_completed += 1

        return hunts_created, tasks_created, tasks_completed

    # ------------------------------------------------------------------
    # step 6: mission briefs
    # ------------------------------------------------------------------

    def _seed_mission_briefs(self, students: List[User]) -> int:
        count = 0
        for student in students:
            try:
                ensure_todays_brief(student)
                count += 1
            except Exception as exc:
                logger.warning(
                    'ensure_todays_brief failed for student %s: %s', student.id, exc,
                )
        return count

    # ------------------------------------------------------------------
    # helpers - logging + summary
    # ------------------------------------------------------------------

    def _log(self, tenant: Tenant, msg: str):
        self.stdout.write(f'[{tenant.slug}] {msg}')

    def _print_summary(self, totals: dict, *, dry_run: bool):
        header = 'Phase B demo seed complete.'
        if dry_run:
            header = 'Phase B demo seed DRY RUN complete (no changes made).'
        bar = '=' * 60
        self.stdout.write('')
        self.stdout.write(bar)
        self.stdout.write(header)
        self.stdout.write(bar)
        self.stdout.write(f"  Tenants processed: {totals['tenants_processed']}")
        self.stdout.write(f"  Enrollments created: {totals['enrollments_created']}")
        self.stdout.write(f"  Demo students onboarded: {totals['demo_students_onboarded']}")
        self.stdout.write(
            f"  Assignments created: {totals['assignments_created']} "
            f"(questions: {totals.get('questions_created', 0)})"
        )
        self.stdout.write(
            f"  Hunts created: {totals['hunts_created']} "
            f"(tasks: {totals['hunt_tasks_created']}, "
            f"completed: {totals['hunt_tasks_completed']})"
        )
        self.stdout.write(f"  XP ledger rows: {totals['xp_ledger_rows']}")
        self.stdout.write(f"  Mission briefs generated: {totals['mission_briefs_generated']}")
        if totals.get('reset_rows_deleted'):
            self.stdout.write(f"  Reset rows deleted: {totals['reset_rows_deleted']}")
        self.stdout.write(bar)
