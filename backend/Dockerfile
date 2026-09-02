FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY backend ./backend
COPY data ./data
RUN pip install --no-cache-dir .

EXPOSE 8001
CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8001"]
