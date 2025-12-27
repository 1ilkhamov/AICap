# AICap Backend
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ ./app/

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Environment
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

EXPOSE 1455

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:1455/health')" || exit 1

# Use 127.0.0.1 by default for security; override with API_HOST env var if needed
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "1455"]
