import json
import logging
import re

from clients.llm import LLMService

logger = logging.getLogger(__name__)


def parse_json_response(text: str) -> dict | list | None:
    """Extract JSON from LLM response, handling markdown code blocks."""
    if not text:
        return None
    # Try direct parse
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting from markdown code block
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Try finding first { ... } or [ ... ]
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = text.find(start_char)
        if start != -1:
            end = text.rfind(end_char)
            if end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass
    logger.warning(f"Failed to parse JSON from LLM response: {text[:200]}")
    return None


class TOCDiscovery:
    """Extracts Table of Contents using text-only LLM call."""

    def __init__(self, llm_service=None):
        self.llm = llm_service or LLMService()

    def discover(self, page_texts: list[dict]) -> dict:
        """Pass raw text of first 30 pages to text-only LLM.
        Returns {document_title, toc: [{chapter, title, printed_page}]}.
        """
        first_pages = page_texts[:30]
        combined = "\n\n---\n\n".join(
            f"[Page {p['pdf_page_index'] + 1}]\n{p['text'][:2000]}"
            for p in first_pages
        )

        prompt = (
            "Here is the raw text from the first 30 pages of a textbook.\n"
            "Extract the Table of Contents if present.\n"
            "Look for patterns like 'Chapter 1 ... page 5' or numbered chapter listings.\n\n"
            f"{combined}\n\n"
            'Return JSON: {"document_title": "...", "toc": '
            '[{"chapter": 1, "title": "...", "printed_page": 1}]}\n'
            'If no TOC found, return {"document_title": "Unknown", "toc": []}.'
        )

        logger.info("Discovering TOC from text...")
        response = self.llm.generate(prompt, max_tokens=2000, temperature=0.1)
        result = parse_json_response(response)

        if not result or "toc" not in result:
            logger.warning("TOC discovery failed — no valid JSON returned")
            return {"document_title": "Unknown", "toc": []}

        toc = result.get("toc", [])
        logger.info(f"Found {len(toc)} chapters in TOC")
        return result
