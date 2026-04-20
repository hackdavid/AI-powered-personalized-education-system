from django.apps import AppConfig


class ServicesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "services"
    verbose_name = "AI Services"

    def ready(self):
        """Pre-load the sentence-transformers embedding model at server startup."""
        from django.conf import settings

        # Avoid running during management commands that don't need it
        import sys
        if "migrate" in sys.argv or "makemigrations" in sys.argv:
            return

        if not getattr(settings, "EMBEDDING_MODEL_PRELOAD", False):
            return

        model_name = getattr(settings, "EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
        from services.ai.embedding_service import init_model
        init_model(model_name)
