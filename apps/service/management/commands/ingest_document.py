"""
Management command to run the ingestion pipeline on a document.

Usage:
    python manage.py ingest_document <document_id>
    python manage.py ingest_document <document_id> --skip-vision
    python manage.py ingest_document <document_id> --max-pages 10
    python manage.py ingest_document --list
"""

import logging

from django.core.management.base import BaseCommand, CommandError
from apps.service.models import Document
from apps.service.services.ingestion.pipeline_orchestrator import IngestionPipeline

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the ingestion pipeline on an uploaded document"

    def add_arguments(self, parser):
        parser.add_argument(
            "document_id",
            nargs="?",
            type=int,
            help="ID of the Document record to ingest",
        )
        parser.add_argument(
            "--skip-vision",
            action="store_true",
            help="Skip vision LLM extraction (text-only mode for testing)",
        )
        parser.add_argument(
            "--max-pages",
            type=int,
            default=None,
            help="Limit processing to first N pages",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="List all documents with their status",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-ingest even if document is already COMPLETED",
        )

    def handle(self, *args, **options):
        # Set up logging to show in console
        logging.basicConfig(level=logging.INFO, format="%(message)s")

        if options["list"]:
            self._list_documents()
            return

        doc_id = options.get("document_id")
        if not doc_id:
            raise CommandError("Please provide a document_id. Use --list to see available documents.")

        try:
            doc = Document.objects.get(id=doc_id)
        except Document.DoesNotExist:
            raise CommandError(f"Document with id={doc_id} not found")

        if doc.status == Document.Status.COMPLETED and not options["force"]:
            self.stdout.write(
                self.style.WARNING(
                    f"Document '{doc.title}' (id={doc_id}) is already COMPLETED. "
                    "Use --force to re-ingest."
                )
            )
            return

        if doc.status == Document.Status.PROCESSING:
            self.stdout.write(
                self.style.WARNING(
                    f"Document '{doc.title}' (id={doc_id}) is currently PROCESSING. "
                    "Wait for it to finish or use --force."
                )
            )
            return

        # Clear previous data if re-ingesting
        if options["force"]:
            from apps.service.models import ContentNode, Asset, ContentCrossRef
            ContentCrossRef.objects.filter(source_node__document=doc).delete()
            Asset.objects.filter(document=doc).delete()
            ContentNode.objects.filter(document=doc).delete()
            self.stdout.write("Cleared previous ingestion data")

        self.stdout.write(self.style.SUCCESS(f"Starting ingestion: '{doc.title}' (id={doc_id})"))
        self.stdout.write(f"  File: {doc.file.path}")
        self.stdout.write(f"  Subject: {doc.subject}")
        self.stdout.write(f"  Skip vision: {options['skip_vision']}")
        self.stdout.write(f"  Max pages: {options['max_pages'] or 'all'}")
        self.stdout.write("")

        pipeline = IngestionPipeline(
            skip_vision=options["skip_vision"],
            max_pages=options["max_pages"],
        )
        stats = pipeline.run(doc_id)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 50))
        self.stdout.write(self.style.SUCCESS("INGESTION COMPLETE"))
        self.stdout.write(self.style.SUCCESS("=" * 50))
        self.stdout.write(f"  Document:  {stats['title']}")
        self.stdout.write(f"  Chapters:  {stats['chapters']}")
        self.stdout.write(f"  Sections:  {stats['sections']}")
        self.stdout.write(f"  Nodes:     {stats['nodes']}")
        self.stdout.write(f"  Assets:    {stats['assets_linked']}")

        if stats["errors"]:
            self.stdout.write("")
            self.stdout.write(self.style.ERROR("ERRORS:"))
            for err in stats["errors"]:
                self.stdout.write(self.style.ERROR(f"  - {err}"))

    def _list_documents(self):
        docs = Document.objects.all().order_by("-created_at")
        if not docs:
            self.stdout.write("No documents found.")
            return

        self.stdout.write(f"{'ID':<6} {'Status':<12} {'Title':<40} {'Subject':<20}")
        self.stdout.write("-" * 80)
        for doc in docs:
            subject = str(doc.subject) if doc.subject else "-"
            self.stdout.write(
                f"{doc.id:<6} {doc.status:<12} {doc.title[:40]:<40} {subject:<20}"
            )
