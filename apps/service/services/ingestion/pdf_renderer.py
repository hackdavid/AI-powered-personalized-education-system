import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class PDFRenderer:
    """Extracts text, renders page images, and pulls embedded assets from PDF."""

    def __init__(self, dpi: int = 200):
        self.dpi = dpi

    def extract_text(self, pdf_path: str) -> list[dict]:
        """Extract raw text from every page.
        Returns [{pdf_page_index, text}].
        """
        import fitz

        doc = fitz.open(pdf_path)
        pages = []
        for i, page in enumerate(doc):
            pages.append({
                "pdf_page_index": i,
                "text": page.get_text(),
            })
        doc.close()
        logger.info(f"Extracted text from {len(pages)} pages")
        return pages

    def render_pages(self, pdf_path: str, output_dir: str) -> list[dict]:
        """Render every PDF page as a PNG image.
        Returns [{pdf_page_index, image_path}].
        """
        import fitz

        doc = fitz.open(pdf_path)
        pages = []
        output = Path(output_dir) / "pages"
        output.mkdir(parents=True, exist_ok=True)

        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=self.dpi)
            img_path = str(output / f"page_{i + 1:03d}.png")
            pix.save(img_path)
            pages.append({
                "pdf_page_index": i,
                "image_path": img_path,
            })
        doc.close()
        logger.info(f"Rendered {len(pages)} page images")
        return pages

    def extract_assets(self, pdf_path: str, output_dir: str) -> list[dict]:
        """Extract embedded images from each page.
        Returns [{page_index, image_path, asset_ref_id, width, height}].
        """
        import fitz

        doc = fitz.open(pdf_path)
        assets = []
        img_output = Path(output_dir) / "images"
        img_output.mkdir(parents=True, exist_ok=True)

        for page_index, page in enumerate(doc):
            images = page.get_images(full=True)
            for img_index, img_info in enumerate(images):
                xref = img_info[0]
                try:
                    base_image = doc.extract_image(xref)
                    if not base_image:
                        continue
                    ref_id = f"page_{page_index + 1:03d}_img_{img_index}"
                    ext = base_image.get("ext", "png")
                    img_path = str(img_output / f"{ref_id}.{ext}")
                    with open(img_path, "wb") as f:
                        f.write(base_image["image"])
                    assets.append({
                        "page_index": page_index,
                        "image_path": img_path,
                        "asset_ref_id": ref_id,
                        "width": base_image.get("width", 0),
                        "height": base_image.get("height", 0),
                    })
                except Exception as e:
                    logger.warning(f"Failed to extract image {img_index} from page {page_index}: {e}")
        doc.close()
        logger.info(f"Extracted {len(assets)} embedded images")
        return assets
