import logging

from clients.llm import LLMService
from apps.service.services.ingestion.toc_discovery import parse_json_response

logger = logging.getLogger(__name__)


class ChapterOutliner:
    """Pass 1: Identifies section boundaries from raw text using text-only LLM."""

    def __init__(self, llm_service=None):
        self.llm = llm_service or LLMService()

    def outline(self, chapter_title: str, chapter_pages: list[dict]) -> list[dict]:
        """Send chapter raw text to text-only LLM.
        Returns [{heading, level, start_pdf_page, end_pdf_page}].
        """
        combined = "\n\n---\n\n".join(
            f"[PDF Page {p['pdf_page_index'] + 1}]\n{p['text'][:3000]}"
            for p in chapter_pages
        )

        prompt = (
            f"Here is the raw text of '{chapter_title}' from a textbook.\n"
            "Identify all section and subsection boundaries.\n"
            "Look for numbered headings (e.g. 5.1, 5.2), bold text, or other heading patterns.\n"
            "Use the [PDF Page N] markers to determine start and end pages.\n\n"
            f"{combined}\n\n"
            'Return JSON array: [{"heading": "5.1 Photosynthesis", '
            '"level": "section", "start_pdf_page": 120, "end_pdf_page": 132}]\n'
            "start_pdf_page and end_pdf_page should be the PDF page INDEX (from the [PDF Page N] markers).\n"
            "If no sections found, return a single entry for the whole chapter."
        )

        logger.info(f"Outlining chapter: {chapter_title}")
        response = self.llm.generate(prompt, max_tokens=2000, temperature=0.1)
        result = parse_json_response(response)

        if not result:
            # Fallback: single section covering the whole chapter
            first_page = chapter_pages[0]["pdf_page_index"]
            last_page = chapter_pages[-1]["pdf_page_index"]
            logger.warning(f"Outline parsing failed, using single section for {chapter_title}")
            return [{
                "heading": chapter_title,
                "level": "section",
                "start_pdf_page": first_page,
                "end_pdf_page": last_page,
            }]

        if isinstance(result, dict):
            result = result.get("sections", result.get("outline", [result]))

        logger.info(f"Found {len(result)} sections in {chapter_title}")
        return result
