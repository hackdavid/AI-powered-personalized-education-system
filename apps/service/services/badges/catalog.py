"""Seed catalog of the 10 starter badges.

Consumed by `apps.service.management.commands.seed_badges`. Each entry is
a kwargs dict for `Badge.objects.update_or_create(code=..., defaults=...)`.
"""

STARTER_BADGES = [
    # ===== AWAKENING =====
    {
        'code': 'first_steps',
        'name': 'First Steps',
        'description': 'Completed the Awakening and entered the System.',
        'icon': '🌅',
        'category': 'awakening',
        'rarity': 'common',
        'criteria': {'type': 'awakening_complete'},
        'display_order': 1,
    },

    # ===== QUESTS =====
    {
        'code': 'quest_novice',
        'name': 'Quest Novice',
        'description': 'Cleared your first Quest.',
        'icon': '📜',
        'category': 'quest',
        'rarity': 'common',
        'criteria': {'type': 'quest_count', 'n': 1},
        'display_order': 10,
    },
    {
        'code': 'quest_master',
        'name': 'Quest Master',
        'description': 'Cleared 10 Quests.',
        'icon': '📚',
        'category': 'quest',
        'rarity': 'rare',
        'criteria': {'type': 'quest_count', 'n': 10},
        'display_order': 11,
    },
    {
        'code': 'perfectionist',
        'name': 'Perfectionist',
        'description': 'Scored 100% on any Quest.',
        'icon': '💯',
        'category': 'quest',
        'rarity': 'rare',
        'criteria': {'type': 'quest_perfect'},
        'display_order': 12,
    },

    # ===== HUNTS =====
    {
        'code': 'hunter',
        'name': 'Hunter',
        'description': 'Cleared your first Hunt.',
        'icon': '🏹',
        'category': 'hunt',
        'rarity': 'common',
        'criteria': {'type': 'hunt_count', 'n': 1},
        'display_order': 20,
    },
    {
        'code': 'warden',
        'name': 'Warden',
        'description': 'Cleared 5 Hunts.',
        'icon': '🏆',
        'category': 'hunt',
        'rarity': 'epic',
        'criteria': {'type': 'hunt_count', 'n': 5},
        'display_order': 21,
    },

    # ===== STREAKS =====
    {
        'code': 'week_warrior',
        'name': 'Week Warrior',
        'description': 'Maintained a 7-day streak.',
        'icon': '🔥',
        'category': 'streak',
        'rarity': 'common',
        'criteria': {'type': 'streak_days', 'n': 7},
        'display_order': 30,
    },
    {
        'code': 'iron_will',
        'name': 'Iron Will',
        'description': 'Maintained a 30-day streak.',
        'icon': '⚡',
        'category': 'streak',
        'rarity': 'epic',
        'criteria': {'type': 'streak_days', 'n': 30},
        'display_order': 31,
    },

    # ===== RANKS =====
    {
        'code': 'ascended_d',
        'name': 'Ascended: D-Rank',
        'description': 'Promoted to Rank D.',
        'icon': '◆',
        'category': 'rank',
        'rarity': 'rare',
        'criteria': {'type': 'rank_reached', 'rank': 'D'},
        'display_order': 40,
    },
    {
        'code': 'ascended_c',
        'name': 'Ascended: C-Rank',
        'description': 'Promoted to Rank C.',
        'icon': '◆',
        'category': 'rank',
        'rarity': 'epic',
        'criteria': {'type': 'rank_reached', 'rank': 'C'},
        'display_order': 41,
    },
]
