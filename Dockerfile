# syntax=docker/dockerfile:1
# ── Stage 1: build wheels ──────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
COPY pyproject.toml ./
COPY app ./app
COPY README.md ./
RUN pip wheel --wheel-dir /wheels .

# ── Stage 2: runtime ───────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=UTC

# Non-root user
RUN groupadd --system app && useradd --system --gid app --create-home app

WORKDIR /app

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels ai-insight-digest \
    && rm -rf /wheels

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

USER app

# Healthcheck: the bot writes a heartbeat file; see app/health.py
HEALTHCHECK --interval=60s --timeout=10s --start-period=20s --retries=3 \
    CMD python -m app.health || exit 1

# CMD (not ENTRYPOINT) so docker-compose's `command:` can cleanly override it
# — e.g. the one-shot `migrate` service runs Alembic instead of the bot.
CMD ["python", "-m", "app"]
