# Student Experience Redesign — "Hunter's System"

> Plan locked 2026-05-03. Phase A in build.
> See also: `project_aim.md`, `todo.md`, `progress.md`.

## TL;DR

Rebuild the student-facing side of the EduAI Platform around a gamified,
anime (Solo Leveling / quest-dungeon) aesthetic fused with the shadcn
direction from `docs/learning-system-design/`. Replace the bland
stat-grid dashboard with a "Status Window"; add a mandatory "Awakening"
calibration flow on first login; frame assignments as "Quests", student
goals as "Hunts" (with LLM-decomposed tasks), layer a persistent daily
"Mission Brief" on top, and re-skin chat as the "System Advisor" with a
curriculum "Codex" side panel.

## Decisions locked

| # | Decision | Impact |
|---|---|---|
| 1 | No email / no token — onboarding wall on login | Middleware redirect to `/student/awakening` until `profile.onboarding_complete=True` |
| 2 | Hard wall — no dashboard access until Awakening done | Only `/student/awakening` + `/auth/logout` escape |
| 3 | Dark-only theme for the student area | `student-theme.css`; `student/_shell.html` forces `class="dark"` |
| 4 | Soft streak — 1 free miss per week | `streak_shields_remaining` refills to 1 every Monday |
| 5 | Persisted Mission Brief | `MissionBrief` + `MissionItem` tables, durable across refreshes |
| 6 | LLM for goal decomposition (stub fallback if no API key) | Matches existing codebase gating |
| 7 | Daily XP cap = 1000 (tunable) | Enforced on `StudentProfile.daily_xp_earned` |

## Theme direction — "Hunter's System × shadcn"

HUD-style dark surfaces with bracketed labels, cyan/violet hairlines,
soft glows. Not cartoony. Palette:

- Cyan `#22d3ee` — system / info / chat
- Violet `#a78bfa` — quests
- Gold `#fbbf24` — XP / rewards
- Crimson `#f43f5e` — urgency
- Emerald `#10b981` — streak / completion

Typography: Geist Sans + Geist Mono (mono for stats / brackets). Motion
short and deliberate; `prefers-reduced-motion` honored. Rank badges are
hex-shaped — E (gray) → D (green) → C (cyan) → B (violet) → A (gold) →
S (holographic).

Admin / teacher / school-admin keep the existing light theme. Dark is
student-only.

## Information architecture

```
/student                  -> Status (replaces current dashboard)
/student/awakening        -> Onboarding / calibration (wall)
/student/quests           -> Assignments list
/student/quests/<id>      -> Quest chamber
/student/hunts            -> Goals list
/student/hunts/<id>       -> Hunt dungeon map
/student/hunts/new        -> Create a hunt
/student/codex            -> Curriculum browser
/student/codex/<node_id>  -> Topic page
/student/chat             -> System Advisor (existing chat, restyled)
/student/profile          -> Hunter card + badges + XP history
```

All share a new `frontend/templates/student/_shell.html` base. A new
`OnboardingRequiredMiddleware` gates the whole namespace.

## Onboarding — "The Awakening"

Hard wall. Partial progress persisted in `OnboardingResult.current_step`
so a closed tab resumes at the same step.

**5 steps**:

1. **Welcome** — narrative intro.
2. **Identity** — hunter_title, avatar, 3-5 interest tags.
3. **Learning style** — 4 VARK MCQs.
4. **Goal** — term goal (template or free text). Becomes the first Hunt at Phase B.
5. **Aptitude probe** — adaptive 5-10 MCQs via existing `QuestionGenerator` + seeded ContentNodes. Stub fallback without API key.

**Awakening cinematic**:

- Calibrated rank: E default; D if overall ≥ 70%; C if ≥ 85%. Never
  higher than C — B+ is earned through play.
- Per-subject mastery = calibration accuracy (0-100).
- `StudentProfile.onboarding_complete=True`; first Hunt created;
  today's Mission Brief generated. Redirect → `/student`.

## Dashboard — "Status Window"

Layout (desktop 12-col; mobile single column):

1. **Hunter Status banner** (top): avatar + name + hunter_title +
   rank badge + level + XP bar + streak.
2. **3-col panel row**: Active Quests count / Mastery bars / Daily
   Streak 7-day grid.
3. **Mission Brief** (durable `MissionItem` list, 3-5 items, same
   across refreshes until completed).
4. **2-col lower row**: Active Quests (top 3) + Active Hunts (top 3).

## Chat — "System Advisor + Codex"

Restyle only. Backend unchanged.

- Dark System sidebar; hunter card footer (name, rank badge, level).
- Assistant bubbles rendered as holographic cards with corner brackets.
- **Codex right-rail** (new): when assistant cites a `ContentNode`, the
  rail loads its full topic page + "Practice this topic" CTA.
- Post-answer CTA: `[ QUEST AVAILABLE ] — +75 XP` for a 5-Q hunt on
  the cited topic.

## Quests (Assignments)

Phase 3 of `todo.md`, relabeled "Quests". Data:

| Model | Key fields |
|---|---|
| `Assignment` | tenant, class, subject, title, description, created_by, due_date, total_marks, difficulty (1-5 stars), reward_xp, is_published |
| `Question` | assignment, type (mcq/short/essay/upload), question_text, options JSON, correct_answer, marks, order |
| `StudentAssignment` | assignment, student, status, submitted_at, score, xp_awarded |
| `Answer` | student_assignment, question, selected_option / answer_text, file, marks_awarded, feedback |

Student flow: List → Quest Chamber (one-Q-at-a-time, autosave every 5 s)
→ Submit (auto-grade MCQ) → Quest Complete overlay + XP.

PDF upload deferred to Phase C.

## Hunts (Student-set goals)

| Model | Key fields |
|---|---|
| `Goal` | student, title, subject?, target_date, status, progress_pct, xp_reward |
| `Task` | goal, title, description, kind, is_completed, order, xp_reward, ref_node_id? |

**Decomposition**: LLM primary (`apps/service/services/hunts/decomposer.py`).
Input: goal + grade + mastery[subject] + top-k ContentNodes + target_date.
Output: JSON 5-8 tasks persisted as `Task` rows. Stub fallback without
API key. Re-decompose rate-limited to 1 / 24 h.

**Dungeon Map**: vertical node map with glowing connecting path.
Completed = gold; current = cyan pulse; final = Boss mini-quiz. Hunt
complete = pass Boss ≥ 70% → big XP payoff.

Expiry: `target_date` past + active → `expired` + partial XP =
`xp_reward × progress_pct`.

## Daily Quests & personal to-dos

**DailyQuest** (system, rule-generated on first login of new day):

- Visit System Advisor (+10)
- Complete 1 Hunt task (+30)
- Practice weakest subject (+50)
- 30 min on-platform (+20)
- Maintain streak (+5)

**Personal to-dos**: free-form reminders; no XP; shown alongside but
visually muted.

## Mission Brief — persistence is the point

Locked decision #5: every mission is authoritative DB state.

| Model | Fields |
|---|---|
| `MissionBrief` | student, date, generated_at, all_completed_at; unique (student, date) |
| `MissionItem` | brief, title, description, kind, xp_reward, priority, status, action_url, related_object_type, related_object_id, completed_at, expires_at |

**Lifecycle**:

- First page hit of a new day → `ensure_todays_brief(student)`: expire
  yesterday's incomplete items, generate today's 3-5 items into DB.
- Every page refresh reads the same items until they're acted on.
- Completing an item → `status=completed`, stays visible dimmed + ✓
  for the rest of the day.
- Teacher publishes urgent quest (< 24 h due) for the student's class →
  insert new `MissionItem` at `priority=999` on today's brief.
- All items done → `all_completed_at` set; dashboard shows "DAILY BRIEF
  CLEARED" card; no auto-top-up until tomorrow.

**Scoring v0** (rule-based; LLM re-rank later):

```
score = urgency + mastery_gap + hunt_relevance + freshness

- Quest due_in < 24h  -> urgency = 100
- Quest due_in < 72h  -> urgency = 50
- Daily quest uncompleted -> urgency = 30
- Hunt next task      -> hunt_relevance = 20 (+10 if target_date close)
- Practice weakest    -> mastery_gap = 100 - mastery_score
```

Top 3-5 by score → persisted as `MissionItem`.

## XP / Level / Rank math

- Level curve: `xp_for_level(N) = floor(100 × N^1.5)`.
  L1=100, L2=283, L5=1118, L10=3162, L20=8944.
- Rank by level: E (1-9) / D (10-19) / C (20-34) / B (35-54) /
  A (55-79) / S (80+). Calibration caps at C.
- Rank-up: 1.2 s full-screen overlay; `profile.recalculate_rank()` on
  every XP event.
- Daily XP cap = 1000 via `profile.daily_xp_earned` reset at midnight.
- `XPLedger` append-only audit (source, amount, related_object_ref).

## Soft streak

- `streak_days` + `streak_shields_remaining` (default 1).
- Daily login check: yesterday had ≥ 1 XP event? → `streak += 1`.
  Else if `shields > 0` → `shields -= 1`, streak preserved + toast.
  Else → `streak = 0`.
- New week: `shields = min(shields + 1, 1)`. One max — prevents hoarding.
- Milestones: 7 d = +100 XP, 30 d = +500 XP.

## Data model additions (summary)

| Model | App | Phase |
|---|---|---|
| `StudentProfile` (1:1 User) | service | A |
| `Enrollment` (Class ↔ User through) | service | A |
| `OnboardingResult` (1:1 User) | service | A |
| `MissionBrief` / `MissionItem` | service | A |
| `Assignment` / `Question` / `StudentAssignment` / `Answer` | service | B |
| `Goal` / `Task` | service | B |
| `DailyQuest` | service | B |
| `XPLedger` | service | B |
| `Badge` (or JSON on profile) | service | C |

All tenant-scoped where applicable; all timestamp-tracked.

## Phased rollout

### Phase A — Foundation

1. Models: StudentProfile, Enrollment, OnboardingResult, MissionBrief,
   MissionItem. Migration + backfill command for existing students
   (default E / L1 / 0 XP / `onboarding_complete=False`).
2. `OnboardingRequiredMiddleware` — the wall.
3. `/student/awakening` — 5-step flow with partial-progress resume.
4. `student/_shell.html` + `student-theme.css` — dark System theme.
5. Restyled `/student` dashboard reading persisted `MissionBrief`.
6. Restyled `/student/chat` (Codex rail + restyle).
7. Mission Brief generator v0 (rule-based).

### Phase B — Close the loop

8. Quests models + teacher UI + student Chamber (MCQ).
9. Hunts models + LLM decomposer + Dungeon Map.
10. DailyQuest generator + midnight rollover.
11. XPLedger + level-up ceremony + daily XP cap.

### Phase C — Polish

12. Badges & ceremony.
13. Streak shield weekly refresh.
14. PDF upload (essay questions).
15. Per-class weekly leaderboard (opt-in, anonymized).
16. Mobile polish.
17. LLM-assisted Mission Brief re-ranker.
