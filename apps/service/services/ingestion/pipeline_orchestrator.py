import logging
import shutil
import tempfile
from pathlib import Path

from apps.service.services.ingestion.pdf_renderer import PDFRenderer
from apps.service.services.ingestion.toc_discovery import TOCDiscovery
from apps.service.services.ingestion.page_calibration import PageCalibrator
from apps.service.services.ingestion.chapter_outliner import ChapterOutliner
from apps.service.services.ingestion.content_structurer import ContentStructurer
from apps.service.services.ingestion.image_linker import ImageLinker
from apps.service.services.ingestion.content_storage import ContentStorage
from apps.service.services.ingestion.cross_ref_builder import CrossRefBuilder
from apps.service.models import ContentNode, Asset
from apps.service.models import Document

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """Orchestrates the full hybrid ingestion pipeline."""

    def __init__(self, skip_vision: bool = False, max_pages: int | None = None):
        self.skip_vision = skip_vision
        self.max_pages = max_pages
        self.renderer = PDFRenderer()
        self.toc_discovery = TOCDiscovery()
        self.calibrator = PageCalibrator()
        self.outliner = ChapterOutliner()
        self.structurer = ContentStructurer()
        self.linker = ImageLinker()
        self.storage = ContentStorage()
        self.cross_refs = CrossRefBuilder()

    def run(self, document_id: int) -> dict:
        """Run the full ingestion pipeline. Returns stats dict."""
        doc = Document.objects.get(id=document_id)
        doc.status = Document.Status.PROCESSING
        doc.save()

        stats = {
            "document_id": document_id,
            "title": doc.title,
            "chapters": 0,
            "sections": 0,
            "nodes": 0,
            "assets_linked": 0,
            "errors": [],
        }

        work_dir = tempfile.mkdtemp(prefix=f"ingest_doc_{document_id}_")

        try:
            # Stage 0: Extract text, render images, extract assets
            logger.info(f"[Stage 0] Extracting from PDF: {doc.file.path}")
            page_texts = self.renderer.extract_text(doc.file.path)

            if self.max_pages:
                page_texts = page_texts[:self.max_pages]
                logger.info(f"  Limited to {self.max_pages} pages")

            page_images = self.renderer.render_pages(doc.file.path, work_dir)
            assets = self.renderer.extract_assets(doc.file.path, work_dir)

            # Apply max_pages limit to images too
            if self.max_pages:
                page_images = page_images[:self.max_pages]

            # Build lookup maps
            image_map = {p["pdf_page_index"]: p["image_path"] for p in page_images}
            text_map = {p["pdf_page_index"]: p for p in page_texts}

            logger.info(f"  {len(page_texts)} pages, {len(assets)} embedded images")

            # Stage 1: TOC + calibration (text-only)
            logger.info("[Stage 1] Discovering TOC...")
            toc = self.toc_discovery.discover(page_texts)
            calibrated = self.calibrator.calibrate(toc, page_texts)
            stats["chapters"] = len(calibrated)

            if not calibrated:
                # No TOC found — treat entire PDF as one chapter
                logger.warning("No chapters found — treating entire PDF as one chapter")
                calibrated = [{
                    "chapter": 1,
                    "title": doc.title,
                    "printed_page": 1,
                    "pdf_page_index": 0,
                }]

            # Stage 2: Chapter structuring
            logger.info(f"[Stage 2] Structuring {len(calibrated)} chapters...")
            all_nodes = []

            for i, chapter_entry in enumerate(calibrated):
                chapter_title = chapter_entry["title"]
                start = chapter_entry["pdf_page_index"]

                # End is start of next chapter, or end of document
                if i + 1 < len(calibrated):
                    end = calibrated[i + 1]["pdf_page_index"]
                else:
                    end = len(page_texts)

                chapter_page_texts = [text_map[j] for j in range(start, end) if j in text_map]
                chapter_page_images = [image_map[j] for j in range(start, end) if j in image_map]

                if not chapter_page_texts:
                    logger.warning(f"  No pages for chapter '{chapter_title}', skipping")
                    continue

                logger.info(f"  Chapter {i + 1}: '{chapter_title}' (pages {start + 1}-{end})")

                # Pass 1: section outline (text-only)
                outline = self.outliner.outline(chapter_title, chapter_page_texts)
                stats["sections"] += len(outline)

                # Ensure section page ranges don't exceed chapter bounds
                for sec in outline:
                    sec["start_pdf_page"] = max(sec.get("start_pdf_page", start), start)
                    sec["end_pdf_page"] = min(sec.get("end_pdf_page", end), end)

                # Create chapter node
                all_nodes.append({
                    "id": str(chapter_entry.get("chapter", i + 1)),
                    "parent_id": None,
                    "node_type": "chapter",
                    "title": chapter_title,
                    "content": "",
                    "page_number": start + 1,
                    "difficulty": None,
                    "images": [],
                    "tables": [],
                })

                # Pass 2: content nodes per section
                if self.skip_vision:
                    logger.info("  Skipping vision (text-only mode)")
                    # Create basic section nodes from outline
                    for sec in outline:
                        sec_start = sec.get("start_pdf_page", start)
                        all_nodes.append({
                            "id": f"{chapter_entry.get('chapter', i + 1)}.{outline.index(sec) + 1}",
                            "parent_id": str(chapter_entry.get("chapter", i + 1)),
                            "node_type": "section",
                            "title": sec["heading"],
                            "content": f"[Section placeholder — vision extraction skipped]",
                            "page_number": sec_start + 1,
                            "difficulty": None,
                            "images": [],
                            "tables": [],
                        })
                    continue

                for j, section in enumerate(outline):
                    sec_start = section.get("start_pdf_page", start)
                    sec_end = section.get("end_pdf_page", end)
                    section_images = [
                        image_map[k]
                        for k in range(sec_start, sec_end)
                        if k in image_map
                    ]

                    if not section_images:
                        logger.warning(f"    No images for section '{section['heading']}', skipping")
                        continue

                    result = self.structurer.structure_section(
                        section_images,
                        section["heading"],
                        chapter_title,
                        str(doc.subject) if doc.subject else "General",
                        start_page_index=sec_start,
                    )

                    section_nodes = result.get("nodes", [])
                    # Set parent_id for section nodes to chapter
                    ch_id = str(chapter_entry.get("chapter", i + 1))
                    for node in section_nodes:
                        if node.get("parent_id") is None and node.get("node_type") == "section":
                            node["parent_id"] = ch_id
                    all_nodes.extend(section_nodes)

            # Stage 3: Link images
            logger.info(f"[Stage 3] Linking {len(all_nodes)} nodes to {len(assets)} assets...")
            all_nodes = self.linker.link(all_nodes, assets)

            # Stage 4: Store + embed
            logger.info(f"[Stage 4] Storing {len(all_nodes)} nodes...")
            self.storage.store(doc, doc.subject, all_nodes, assets)
            stats["nodes"] = len(all_nodes)
            stats["assets_linked"] = Asset.objects.filter(document=doc).count()

            # Stage 5: Cross-references
            logger.info("[Stage 5] Building cross-references...")
            self.cross_refs.build(doc)

            doc.status = Document.Status.COMPLETED
            doc.save()

            logger.info(f"[DONE] Document {document_id} ingested successfully")

        except Exception as e:
            logger.exception(f"[FAILED] Document {document_id} ingestion failed")
            stats["errors"].append(str(e))
            doc.status = Document.Status.FAILED
            doc.save()

        finally:
            # Clean up temp directory
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
            except Exception:
                pass

        return stats
