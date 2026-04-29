"""
Offline stub answerer.

Used when no `OPENAI_API_KEY` is configured. The tutor honestly tells the
student it is in offline mode and shows the top retrieved sources verbatim
with their citation numbers. No fake reasoning is produced.
"""

from typing import List

from .retriever import RetrievedChunk

STUB_MODEL_NAME = 'stub'


def answer(query: str, hits: List[RetrievedChunk]) -> str:
    """Build an offline-mode answer string from retrieved sources."""
    if not hits:
        return (
            "I'm running in offline mode and could not find any matching "
            "curriculum content for your question. Please ask a school admin "
            "to enable the AI tutor or rephrase your question."
        )

    lines = [
        "I'm currently running in offline mode (no LLM configured), so here "
        "are the most relevant passages from your curriculum:",
        '',
    ]
    for i, hit in enumerate(hits, start=1):
        page = f' (p. {hit.page_number})' if hit.page_number else ''
        lines.append(f'[{i}] {hit.title}{page}')
        if hit.snippet:
            lines.append(hit.snippet)
        lines.append('')
    return '\n'.join(lines).rstrip()
