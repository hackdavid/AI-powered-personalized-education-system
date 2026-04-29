import logging

logger = logging.getLogger(__name__)


class ImageLinker:
    """Matches LLM image references to pymupdf-extracted image files."""

    def link(self, nodes: list[dict], assets: list[dict]) -> list[dict]:
        """Join on asset_ref_id (e.g. 'page_121_img_0')."""
        asset_map = {a["asset_ref_id"]: a["image_path"] for a in assets}
        linked_count = 0

        for node in nodes:
            for img in node.get("images", []):
                ref_id = img.get("reference_id", "")
                if ref_id in asset_map:
                    img["file_path"] = asset_map[ref_id]
                    img["linked"] = True
                    linked_count += 1
                else:
                    img["linked"] = False

        logger.info(f"Linked {linked_count} images to extracted files")
        return nodes
