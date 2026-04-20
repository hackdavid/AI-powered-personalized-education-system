"""
AI-powered question generation service.
Uses LLMService to create educational assessment questions.
"""

import json
import logging
import re
from typing import Dict, List, Optional

from services.ai.llm_service import LLMService

logger = logging.getLogger(__name__)

QUESTION_TYPES = ("mcq", "true_false", "short_answer", "essay")
DIFFICULTY_LEVELS = ("easy", "medium", "hard")


class QuestionGenerator:
    """Generates educational questions using an LLM."""

    def __init__(self, llm_service: Optional[LLMService] = None):
        self.llm = llm_service or LLMService()

    def generate_questions(
        self,
        topic: str,
        difficulty: str = "medium",
        count: int = 5,
        question_type: str = "mcq",
        subject_context: str = "",
    ) -> List[Dict]:
        """Generate educational questions on a given topic.

        Returns a list of dicts with keys: question, options, correct_answer, explanation.
        """
        if difficulty not in DIFFICULTY_LEVELS:
            raise ValueError(f"Invalid difficulty: {difficulty}. Use: {DIFFICULTY_LEVELS}")
        if question_type not in QUESTION_TYPES:
            raise ValueError(f"Invalid question_type: {question_type}. Use: {QUESTION_TYPES}")

        system = (
            "You are an expert educator creating assessment questions. "
            "Return ONLY a valid JSON array — no markdown, no commentary."
        )

        prompt = self._build_prompt(topic, difficulty, count, question_type, subject_context)
        raw = self.llm.generate(prompt=prompt, system=system, temperature=0.7, max_tokens=2000)

        return self._parse_response(raw, question_type)

    def _build_prompt(
        self, topic: str, difficulty: str, count: int, question_type: str, subject_context: str
    ) -> str:
        context_line = f"\nSubject context: {subject_context}" if subject_context else ""

        if question_type == "mcq":
            schema = (
                '{"question": "...", "options": ["A) ...", "B) ...", "C) ...", "D) ..."], '
                '"correct_answer": "A) ...", "explanation": "..."}'
            )
        elif question_type == "true_false":
            schema = (
                '{"question": "...", "options": ["True", "False"], '
                '"correct_answer": "True/False", "explanation": "..."}'
            )
        elif question_type == "short_answer":
            schema = (
                '{"question": "...", "options": [], '
                '"correct_answer": "...", "explanation": "..."}'
            )
        else:  # essay
            schema = (
                '{"question": "...", "options": [], '
                '"correct_answer": "key points to cover", "explanation": "marking guidelines"}'
            )

        return (
            f"Generate exactly {count} {difficulty}-difficulty {question_type} questions "
            f"on the topic: {topic}.{context_line}\n\n"
            f"Format each question as a JSON object matching this schema:\n{schema}\n\n"
            "Return ONLY a JSON array of question objects. No extra text."
        )

    def _parse_response(self, raw: str, question_type: str) -> List[Dict]:
        """Extract and validate JSON from the LLM response."""
        # Strip markdown code fences if present
        cleaned = re.sub(r"```json\s*", "", raw)
        cleaned = re.sub(r"```\s*", "", cleaned)
        cleaned = cleaned.strip()

        try:
            questions = json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to find a JSON array in the response
            match = re.search(r"\[.*\]", cleaned, re.DOTALL)
            if match:
                questions = json.loads(match.group())
            else:
                logger.error("Failed to parse question JSON from LLM response")
                return []

        if not isinstance(questions, list):
            questions = [questions]

        # Validate and normalize each question
        validated = []
        for q in questions[:50]:  # safety cap
            if not isinstance(q, dict) or "question" not in q:
                continue
            validated.append({
                "question": q.get("question", ""),
                "options": q.get("options", []),
                "correct_answer": q.get("correct_answer", ""),
                "explanation": q.get("explanation", ""),
                "type": question_type,
                "difficulty": q.get("difficulty", ""),
            })

        return validated
