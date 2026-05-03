# ──────────────────────────────────────────────
# Backend Dockerfile — FastAPI + Uvicorn
# Multi-stage build for minimal production image
# ──────────────────────────────────────────────

# ── Stage 1: Build dependencies ──────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build-time system deps (needed for psycopg2-binary, etc.)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install Python packages into a virtual-env so we can copy it cleanly
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# ── Stage 2: Production runtime ──────────────
FROM python:3.12-slim AS runtime

# Runtime system libs (libpq for psycopg2)
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 curl && \
    rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# Copy the pre-built virtual-env from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application source
COPY . .

# Remove dev artifacts that shouldn't be in prod
RUN rm -rf venv .venv __pycache__ *.sqlite* *.db*

# Own everything by appuser
RUN chown -R appuser:appuser /app

USER appuser

# Uvicorn production settings
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--proxy-headers", "--forwarded-allow-ips", "*"]
