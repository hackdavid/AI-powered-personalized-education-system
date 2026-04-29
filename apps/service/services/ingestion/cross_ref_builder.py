import logging

from clients.llm import LLMService
from apps.service.models import ContentNode, ContentCrossRef
from apps.service.services.ingestion.toc_discovery import parse_json_response

logger = logging.getLogger(__name__)


class CrossRefBuilder:
    """Builds cross-references between content nodes via text LLM."""

    def build(self, document, llm_service=None):
        llm = llm_service or LLMService()
        chapters = ContentNode.objects.filter(
            document=document, node_type="chapter"
        ).order_by("position")

        if not chapters.exists():
            logger.info("No chapter nodes found — skipping cross-references")
            return

        total_refs = 0
        for chapter in chapters:
            descendants = chapter.get_descendants()
            if not descendants:
                continue

            titles = [
                f"{n.node_id} {n.title} [{n.node_type}]"
                for n in descendants[:100]  # cap to avoid token bloat
            ]

            other_chapters = chapters.exclude(id=chapter.id)
            other_titles = []
            for oc in other_chapters:
                other_titles.append(f"\n{oc.node_id} {oc.title}:")
                for n in oc.get_descendants()[:20]:
                    other_titles.append(f"  {n.node_id} {n.title}")

            prompt = (
                f"Chapter '{chapter.title}' has these topics:\n"
                + "\n".join(titles)
                + "\n\nOther chapters:\n" + "\n".join(other_titles)
                + "\n\nIdentify prerequisite and cross-reference relationships. "
                'Return JSON array: [{"source_id": "5.1.3", "target_id": "1.2.1", '
                '"ref_type": "prerequisite", "description": "..."}]\n'
                "ref_type must be one of: prerequisite, related, extends, applies\n"
                "If no meaningful relationships exist, return []."
            )

            response = llm.generate(prompt, max_tokens=2000, temperature=0.1)
            refs = parse_json_response(response)

            if not refs:
                continue

            if isinstance(refs, dict):
                refs = refs.get("references", refs.get("refs", []))

            for ref in refs:
                source = ContentNode.objects.filter(
                    document=document, node_id=ref.get("source_id")
                ).first()
                target = ContentNode.objects.filter(
                    document=document, node_id=ref.get("target_id")
                ).first()
                if source and target:
                    ContentCrossRef.objects.get_or_create(
                        tenant=document.tenant,
                        source_node=source,
                        target_node=target,
                        ref_type=ref.get("ref_type", "related"),
                        defaults={"description": ref.get("description", "")},
                    )
                    total_refs += 1

        logger.info(f"Created {total_refs} cross-references")
