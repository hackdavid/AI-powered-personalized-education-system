# Creates the `ContentEmbedding` table + HNSW cosine index.
#
# HNSW is added via a RunPython conditional on PostgreSQL so that
# SQLite test databases (which don't understand `WITH (...)` index
# syntax) can still apply this migration cleanly. On Postgres we emit
# the real CREATE INDEX ... USING hnsw statement; on other backends
# this is a silent no-op.

import django.db.models.deletion
import pgvector.django.vector
from django.db import migrations, models
from pgvector.django import VectorExtension


HNSW_INDEX_NAME = "content_emb_hnsw_cos"


def create_hnsw_index_on_postgres(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        f"""
        CREATE INDEX IF NOT EXISTS {HNSW_INDEX_NAME}
        ON service_contentembedding
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
        """
    )


def drop_hnsw_index_on_postgres(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(f"DROP INDEX IF EXISTS {HNSW_INDEX_NAME};")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        ("service", "0003_tutoringsession_chatmessage_and_more"),
    ]

    operations = [
        # Idempotent `CREATE EXTENSION IF NOT EXISTS vector`. Supabase has
        # pgvector pre-installed but it must be enabled per project.
        # No-op on non-Postgres backends.
        VectorExtension(),
        migrations.CreateModel(
            name="ContentEmbedding",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("embedding", pgvector.django.vector.VectorField(dimensions=384)),
                (
                    "model_name",
                    models.CharField(
                        help_text="Embedding model identifier, e.g. all-MiniLM-L6-v2.",
                        max_length=64,
                    ),
                ),
                (
                    "embedding_id",
                    models.CharField(blank=True, db_index=True, max_length=128),
                ),
                (
                    "content_node",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="embeddings",
                        to="service.contentnode",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(class)s_set",
                        to="accounts.tenant",
                    ),
                ),
            ],
            options={
                "verbose_name": "Content embedding",
                "verbose_name_plural": "Content embeddings",
                "indexes": [
                    models.Index(
                        fields=["tenant", "model_name"],
                        name="service_con_tenant__7e0398_idx",
                    ),
                ],
                "unique_together": {("content_node", "model_name")},
            },
        ),
        migrations.RunPython(
            create_hnsw_index_on_postgres,
            drop_hnsw_index_on_postgres,
        ),
    ]
