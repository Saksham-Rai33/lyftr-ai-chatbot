# ---- build stage: resolve and install dependencies into an isolated prefix ----
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY requirements.txt .
RUN pip install --prefix=/install -r requirements.txt \
    # drop LiteLLM's bundled proxy-dashboard static assets (unused; we only use the SDK)
    && rm -rf /install/lib/python3.12/site-packages/litellm/proxy/_experimental/out \
    && find /install -name "__pycache__" -type d -prune -exec rm -rf {} +

# ---- runtime stage: slim image, non-root user, no build tooling ----
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////data/app.db \
    PORT=8000
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data \
    && chown appuser:appuser /data
COPY --from=builder /install /usr/local
WORKDIR /app
COPY --chown=appuser:appuser app ./app
USER appuser
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8000'))"
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
