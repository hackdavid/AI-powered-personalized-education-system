# EduAI Platform — production runtime image.
#
# Single-stage build using python:3.12-slim. Stack:
#   * Django 5 + DRF
#   * Gunicorn (sync workers; tutoring is I/O-bound but small)
#   * WhiteNoise to serve collected static files (no separate nginx)
#   * psycopg2-binary against Supabase pgvector
#
# Render-specific notes:
#   * Render injects $PORT (usually 10000). We bind to it; falls back to
#     8000 if running plain `docker run` locally.
#   * Migrations run as a Render preDeployCommand (see render.yaml), not
#     in this image, so a deploy never serves traffic against an
#     out-of-date schema.
#   * collectstatic happens at build time so the image is fully
#     self-contained at runtime.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings \
    PORT=8000

WORKDIR /app

# Build / runtime system deps:
#   build-essential + libpq-dev: in case any wheel has to compile against libpq
#   curl: small but useful for `docker exec`-style debugging in Render shell
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps first so `pip install` is cached when only code changes.
COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Copy the project source.
COPY . .

# Collect static files into STATIC_ROOT (BASE_DIR/staticfiles). WhiteNoise
# serves them at /static/ in production. This step needs Django to load,
# but does NOT touch the DB; we feed dummy values so it stays self-contained.
RUN DJANGO_DEBUG=False \
    DJANGO_SECRET_KEY=build-time-only-not-used-at-runtime \
    DJANGO_ALLOWED_HOSTS=* \
    DATABASE_URL='postgresql://nobody:nobody@127.0.0.1:5432/none' \
    python manage.py collectstatic --noinput

# logs/ is referenced by the JSON log handler in settings.py; create it
# at build time so the runtime user doesn't need write perms on /app.
RUN mkdir -p logs && chmod 0777 logs

EXPOSE 8000

# Gunicorn config:
#   * 2 sync workers — fits Render free tier RAM (512 MB)
#   * --timeout 60 — gives slow LLM calls headroom (we use 30s in client too)
#   * --access-logfile - / --error-logfile - — stream logs to stdout/stderr
#     where Render captures them
CMD ["sh", "-c", "gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 60 --access-logfile - --error-logfile -"]
