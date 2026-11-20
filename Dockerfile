# syntax=docker/dockerfile:1.7
# ---------- 1. build the React frontend ----------
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- 2. runtime: FastAPI + PyTorch (CPU by default) ----------
FROM python:3.13-slim-bookworm AS app
ARG TORCH_INDEX=https://download.pytorch.org/whl/cpu
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PD_ENV=production PD_DATA_DIR=/data PD_LOG_JSON=1
RUN useradd --create-home --uid 10001 app
WORKDIR /app
COPY requirements.txt .
RUN pip install torch==2.11.0 torchvision==0.26.0 --index-url ${TORCH_INDEX} \
 && pip install -r requirements.txt
COPY app/ app/
COPY ml/ ml/
COPY alembic/ alembic/
COPY alembic.ini .
COPY models/ models/
COPY reports/*.json reports/
COPY reports/PlantDoctor_Report.pdf reports/
COPY --from=web /web/dist frontend/dist
RUN mkdir -p /data && chown -R app:app /data
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/ready',timeout=4).status==200 else 1)"
# Migrations run on startup (app.server.lifespan). One worker: the model and rate limiter are in-process.
CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
