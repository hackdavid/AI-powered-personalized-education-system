"""XP ledger service — awards XP and enforces the daily cap.

Every XP-earning action calls `award_xp()`. Direct manipulation of
StudentProfile.total_xp / level / rank is forbidden outside this module.
"""

from .ledger import award_xp, get_recent_xp_events, XPAwardResult

__all__ = ['award_xp', 'get_recent_xp_events', 'XPAwardResult']
