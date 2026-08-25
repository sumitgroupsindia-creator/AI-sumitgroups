FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# libmagic1 for MIME sniffing, curl for the container healthcheck. No compilers: every pinned
# dependency ships manylinux wheels, and build-essential would add ~350MB for nothing.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libmagic1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user; it must own the storage mount to be able to write uploads.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/storage/images/generated /app/storage/images/uploaded \
                /app/storage/images/thumbnails /app/storage/temp \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--proxy-headers", "--forwarded-allow-ips", "*"]
