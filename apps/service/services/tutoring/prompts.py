"""System prompts for the tutoring service."""

TUTOR_SYSTEM_PROMPT = (
    "You are an AI tutor for school students. Answer the student's question "
    "using ONLY the provided curriculum context. "
    "Cite supporting context with bracketed numbers like [1] or [2] that "
    "match the numbered context entries. If the context does not contain "
    "enough information, say so plainly rather than guessing. "
    "Keep the tone encouraging and explain in language appropriate for the "
    "student's grade level when known."
)


def build_system_prompt(grade_level: int | None = None) -> str:
    """Return the system prompt, optionally tailored to a student grade level."""
    if grade_level is None:
        return TUTOR_SYSTEM_PROMPT
    return f"{TUTOR_SYSTEM_PROMPT}\n\nThe student is in grade {grade_level}; calibrate vocabulary and depth accordingly."
