FROM python:3.11-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System dependencies for scientific packages and PostgreSQL
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libgeos-dev \
    libgdal-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── Builder stage ─────────────────────────────────────────────────────────────
FROM base AS builder

# Copy project config and source — separate layers for cache efficiency
COPY pyproject.toml .
COPY backend/ backend/

RUN pip install --upgrade pip && pip install .

# ── Final image ───────────────────────────────────────────────────────────────
FROM base AS final

# Non-root user for security
RUN groupadd -r losapp && useradd -r -g losapp losapp

# Copy installed packages and entrypoints from builder
COPY --from=builder /usr/local/lib/python3.11 /usr/local/lib/python3.11
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app

# Copy full project (needed for alembic migrations and static assets)
COPY --chown=losapp:losapp . .

USER losapp

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "4", "--loop", "uvloop", "--http", "h11"]
