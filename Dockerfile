# Single-container build: React SPA compiled and served by the FastAPI app.
FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
WORKDIR /app
COPY backend/pyproject.toml backend/
COPY backend/rig backend/rig
COPY backend/migrations backend/migrations
RUN pip install --no-cache-dir ./backend
COPY --from=frontend /build/dist frontend/dist
ENV RIG_FRONTEND_DIST=/app/frontend/dist
EXPOSE 8000
CMD ["sh", "-c", "python -m rig.boot && uvicorn rig.main:app --host 0.0.0.0 --port 8000"]
