"""Public API of the tutoring service package."""

from .catalog import SubjectCatalog, get_student_catalog, invalidate_catalog
from .prompts import TutorUnavailable, UNAVAILABLE_MESSAGE
from .retriever import CurriculumRetriever, RetrievedChunk
from .router import QueryRouter, Routing
from .tutor_service import TutorAnswer, TutorService

__all__ = [
    'CurriculumRetriever',
    'QueryRouter',
    'RetrievedChunk',
    'Routing',
    'SubjectCatalog',
    'TutorAnswer',
    'TutorService',
    'TutorUnavailable',
    'UNAVAILABLE_MESSAGE',
    'get_student_catalog',
    'invalidate_catalog',
]
