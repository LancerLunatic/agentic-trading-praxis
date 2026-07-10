# ---- Agentic Trading Praxis :: Public Dashboard image (Cloud Run) ----
# Serves the read-only decision-logic dashboard. Runs in mock/simulation
# mode only — no live trading occurs from this container.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

# Install deps first for layer caching
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy application code (respecting .dockerignore)
COPY . .

EXPOSE 8080

# Cloud Run injects $PORT. Serve the FastAPI dashboard app.
CMD exec uvicorn dashboard.server:app --host 0.0.0.0 --port ${PORT}
