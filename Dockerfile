FROM node:22-alpine AS frontend-build

WORKDIR /app
RUN corepack enable && corepack prepare pnpm@11.19.0 --activate
COPY frontend/package.json frontend/pnpm-workspace.yaml ./frontend/
RUN cd frontend && pnpm install --no-frozen-lockfile
COPY frontend ./frontend
RUN cd frontend && pnpm build

FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY backend ./backend
COPY data ./data
COPY --from=frontend-build /app/frontend/dist ./frontend/dist
RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port \"${PORT:-8000}\""]
