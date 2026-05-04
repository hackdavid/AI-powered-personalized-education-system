from .academic import Subject, Class, ClassSubject
from .document import Document
from .content_node import ContentNode
from .asset import Asset
from .cross_reference import ContentCrossRef
from .tutoring import TutoringSession, ChatMessage
from .embedding import ContentEmbedding, EMBEDDING_DIM

# Phase A
from .student_profile import StudentProfile
from .enrollment import Enrollment
from .onboarding import OnboardingResult
from .missions import MissionBrief, MissionItem

# Phase B
from .assignments import Assignment, Question, StudentAssignment, Answer
from .hunts import Goal, Task
from .daily_quests import DailyQuest
from .xp_ledger import XPLedger

# Phase C
from .badges import Badge, EarnedBadge

__all__ = [
    'Subject', 'Class', 'ClassSubject', 'Document',
    'ContentNode', 'Asset', 'ContentCrossRef',
    'TutoringSession', 'ChatMessage',
    'ContentEmbedding', 'EMBEDDING_DIM',

    'StudentProfile', 'Enrollment', 'OnboardingResult',
    'MissionBrief', 'MissionItem',

    'Assignment', 'Question', 'StudentAssignment', 'Answer',
    'Goal', 'Task', 'DailyQuest', 'XPLedger',

    'Badge', 'EarnedBadge',
]
