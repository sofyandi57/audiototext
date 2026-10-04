# syntax=docker/dockerfile:1
# Single image: FastAPI API + static Next.js frontend + worker (CPU only).
#   docker build -t meeting-intel .                      # without ASR (small)
#   docker build -t meeting-intel --build-arg WITH_ASR=1 .  # + faster-whisper

FROM node:22-bookworm-slim AS web
WORKDIR /web
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 NEXT_TELEMETRY_DISABLED=1
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=secret,id=ca_bundle,required=false \
    if [ -f /run/secrets/ca_bundle ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/ca_bundle; fi \
 && npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM ubuntu:24.04
ARG WITH_ASR=0
ENV DEBIAN_FRONTEND=noninteractive \
    PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MI_DATA_DIR=/data \
    MI_FRONTEND_DIR=/app/frontend/out \
    MI_WHISPER_DOWNLOAD_ROOT=/data/models \
    HF_HOME=/data/models/hf
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
      ffmpeg espeak-ng tesseract-ocr tesseract-ocr-ind tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/* \
 && python3 -m venv /opt/venv
WORKDIR /app/backend
COPY backend/requirements*.txt ./
# Behind a TLS-inspecting proxy, pass its CA: --secret id=ca_bundle,src=/path/ca.crt
RUN --mount=type=secret,id=ca_bundle,required=false \
    if [ -f /run/secrets/ca_bundle ]; then export PIP_CERT=/run/secrets/ca_bundle; fi \
 && pip install --no-cache-dir -r requirements.txt \
 && if [ "$WITH_ASR" = "1" ]; then pip install --no-cache-dir -r requirements-asr.txt; fi
COPY backend/ ./
COPY --from=web /web/out /app/frontend/out
RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown app /data
USER app
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + __import__('os').environ.get('PORT', '8000') + '/api/health')"
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
