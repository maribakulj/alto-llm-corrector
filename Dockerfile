# Stage 1 — Build React frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /frontend
COPY frontend/package*.json .
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2 — Python backend + static frontend
FROM python:3.11-slim
WORKDIR /app

# Install Python dependencies first (separate layer for caching).
# requirements.txt is pinned so Docker's content-based cache invalidation
# works correctly — changing any pin forces a full pip reinstall.
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app/ ./app/
COPY --from=frontend-builder /frontend/dist ./static/

ENV JOB_STORAGE_DIR=/tmp/app-jobs

EXPOSE 7860

# Explicit health check so HF Spaces / Docker knows when the app is ready.
# /health returns {"status":"ok"} immediately; no dependency on static files.
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD python -c \
    "import urllib.request; urllib.request.urlopen('http://localhost:7860/health')" \
  || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
