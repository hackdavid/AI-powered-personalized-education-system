import logging

logger = logging.getLogger(__name__)


class PageCalibrator:
    """Maps printed page numbers to PDF page indices using text matching."""

    def calibrate(self, toc: dict, page_texts: list[dict]) -> list[dict]:
        """For each chapter in TOC, find which PDF page it starts on.
        Uses text-based matching: search for chapter title in page text.
        Returns [{chapter, title, printed_page, pdf_page_index}].
        """
        calibrated = []
        for entry in toc.get("toc", []):
            title = entry.get("title", "")
            chapter_num = entry.get("chapter")
            pdf_index = self._find_chapter_page(title, chapter_num, page_texts)
            calibrated.append({
                **entry,
                "pdf_page_index": pdf_index,
            })
            if pdf_index is not None:
                logger.info(f"Chapter {chapter_num} '{title}' → PDF page {pdf_index + 1}")
            else:
                logger.warning(f"Chapter {chapter_num} '{title}' → NOT FOUND")
        return calibrated

    def _find_chapter_page(self, title: str, chapter_num: int, page_texts: list[dict]) -> int | None:
        """Search page texts for the chapter heading. Returns first match."""
        title_lower = title.lower().strip()
        candidates = []

        for page in page_texts:
            text = page["text"].lower()

            # Primary match: "Chapter N" or "Chapter N:" or "CHAPTER N"
            if chapter_num is not None:
                for pattern in [
                    f"chapter {chapter_num}",
                    f"chapter{chapter_num}",
                    f"chapter  {chapter_num}",
                ]:
                    if pattern in text:
                        candidates.append(page["pdf_page_index"])
                        break

            # Secondary match: chapter title in text
            if title_lower and len(title_lower) > 5 and title_lower in text:
                idx = page["pdf_page_index"]
                if idx not in candidates:
                    candidates.append(idx)

        if candidates:
            return candidates[0]
        return None
