# Backend service (FastAPI + run workers). Railway: root directory = backend, this Dockerfile.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
COPY triage ./triage
COPY api ./api
COPY alembic ./alembic
COPY alembic.ini ./
COPY samples ./samples
RUN pip install --upgrade pip && pip install ".[server]"
ENV TRIAGE_DATA_DIR=/data STORAGE_BACKEND=local PORT=8000
EXPOSE 8000
# Migrations run on every boot (idempotent); then the API with its in-process run workers.
CMD alembic upgrade head && uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'
