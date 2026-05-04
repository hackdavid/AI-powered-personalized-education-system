"""Mission Brief generator — rule-based, persisted.

See docs/student-redesign.md for the lifecycle and scoring rules. All
generated items are written to the MissionItem table so dashboard reads
are idempotent across page refreshes.
"""

from .generator import (
    ensure_todays_brief,
    generate_mission_brief,
    expire_old_briefs,
    mark_item_completed_for_event,
)

__all__ = [
    'ensure_todays_brief', 'generate_mission_brief', 'expire_old_briefs',
    'mark_item_completed_for_event',
]
