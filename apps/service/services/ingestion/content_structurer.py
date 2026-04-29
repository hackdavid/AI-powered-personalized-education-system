import base64
import logging

from clients.llm import LLMService
from apps.service.services.ingestion.toc_discovery import parse_json_response

logger = logging.getLogger(__name__)

LATEX_RULES = """
LATEX RULES (CRITICAL — FOLLOW EXACTLY):
- ALL math expressions MUST be in LaTeX
- Inline math: single dollar signs $x^2$
- Block equations: double dollar signs $$...$$
- Fractions: \\frac{numerator}{denominator}
- Subscripts: H_{2}O (always use braces, even for single chars)
- Superscripts: x^{2} (always use braces)
- Greek letters: \\alpha, \\beta, \\gamma, \\theta
- Chemical arrows: \\xrightarrow{light energy}
- Sums/integrals: \\sum_{i=1}^{n}, \\int_{a}^{b}
- Square roots: \\sqrt{x} or \\sqrt[n]{x}
- DO NOT use Unicode math symbols
- DO NOT simplify or rewrite equations
- Preserve the EXACT equation from the source"""


class ContentStructurer:
    """Pass 2: Extracts content nodes using vision LLM, one page at a time with rolling summary."""

    PAGE_PROMPT = """You are extracting content from a {subject} textbook, section "{section_title}".

PREVIOUSLY EXTRACTED (use this for context and continuity):
{rolling_summary}

Last node id used: {last_node_id}

Now extract ALL content from THIS page as content nodes.

{latex_rules}

Each node:
- id: unique within chapter (continue from {last_node_id})
- parent_id: null for section-level, parent's id for children
- node_type: section | topic | definition | formula | example | exercise | summary | key_point
- title: short descriptive title
- content: markdown with LaTeX for ALL math
- difficulty: basic | intermediate | advanced
- page_number: {page_number}
- images: [{{"position": "top-left", "description": "...", "label": "Figure X", "reference_id": "page_XXX_img_N"}}]
- tables: [{{"description": "...", "markdown": "..."}}]

Rules:
- Each node = ONE concept (sub-atomic)
- Preserve hierarchy from the page layout
- When you see a diagram/image, describe it and note position
- ALL equations, formulas, and math → LaTeX (see rules above)
- Mark node types explicitly
- Reference images as page_XXX_img_N where XXX is the PDF page number (1-indexed)

Return: {{"nodes": [...], "summary": "brief text summary of this page"}}"""

    def __init__(self, llm_service=None):
        self.llm = llm_service or LLMService()

    def structure_section(
        self,
        section_pages: list[str],
        section_title: str,
        chapter_title: str,
        subject: str,
        start_page_index: int = 0,
    ) -> dict:
        """Process section pages sequentially with rolling summary.
        Returns {section, nodes: [...]}.
        """
        all_nodes = []
        rolling_summary = "Nothing extracted yet — this is the first page."
        last_node_id = section_title.split()[0] if section_title else "0"

        for page_idx, page_path in enumerate(section_pages):
            pdf_page_num = start_page_index + page_idx + 1
            logger.info(f"  Processing page {pdf_page_num} ({page_idx + 1}/{len(section_pages)})...")

            result = self._process_page(
                page_path, section_title, subject,
                rolling_summary, last_node_id, pdf_page_num,
            )

            if result:
                nodes = result.get("nodes", [])
                all_nodes.extend(nodes)

                page_summary = result.get("summary", "")
                node_list = ", ".join(
                    f"{n['id']} ({n.get('node_type', '?')})" for n in nodes
                )
                rolling_summary = (
                    f"{rolling_summary}\n\n"
                    f"Page {pdf_page_num} summary: {page_summary}\n"
                    f"Nodes extracted: {node_list}"
                )
                # Cap rolling summary to avoid token bloat
                if len(rolling_summary) > 3000:
                    rolling_summary = rolling_summary[-3000:]

                if nodes:
                    last_node_id = nodes[-1].get("id", last_node_id)

        logger.info(f"  Section '{section_title}': {len(all_nodes)} nodes extracted")
        return {"section": section_title, "nodes": all_nodes}

    def _process_page(
        self, page_path: str, section_title: str, subject: str,
        rolling_summary: str, last_node_id: str, page_number: int,
    ) -> dict | None:
        """Send ONE page image + rolling text summary to vision LLM."""
        prompt = self.PAGE_PROMPT.format(
            subject=subject,
            section_title=section_title,
            rolling_summary=rolling_summary[:2000],
            last_node_id=last_node_id,
            latex_rules=LATEX_RULES,
            page_number=page_number,
        )

        try:
            b64 = base64.b64encode(open(page_path, "rb").read()).decode()
        except Exception as e:
            logger.error(f"Failed to read page image {page_path}: {e}")
            return None

        content = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            },
        ]

        try:
            response = self.llm.client.chat.completions.create(
                model=self.llm._model_name,
                messages=[{"role": "user", "content": content}],
                max_tokens=3000,
                temperature=0.1,
            )
            raw = response.choices[0].message.content
            return parse_json_response(raw)
        except Exception as e:
            logger.error(f"Vision LLM call failed for page {page_number}: {e}")
            return None
