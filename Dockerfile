# syntax=docker/dockerfile:1
# Multi-stage build for the rag_platform package.
# Produces image: ghcr.io/your-org/rag-platform (see helm/values.yaml).

# ---- build stage ----
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- runtime stage ----
FROM python:3.12-slim AS runtime

# Security: run as a dedicated non-root user.
RUN groupadd --gid 1001 appgroup \
    && useradd --uid 1001 --gid appgroup --no-create-home appuser

WORKDIR /app

# Installed dependencies from the build stage.
COPY --from=builder /install /usr/local

# Application source (src layout).
COPY src/ ./src/

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    RAGPLATFORM_HOST=0.0.0.0 \
    RAGPLATFORM_PORT=8000

USER appuser

EXPOSE 8000

# Container-level health probe (mirrors the Kubernetes liveness probe).
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "rag_platform.main:app", "--host", "0.0.0.0", "--port", "8000"]
