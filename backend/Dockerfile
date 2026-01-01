# AICap Backend
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ ./app/
COPY run_server.py .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Environment
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO
ENV API_HOST=0.0.0.0
ENV API_PORT=1455

EXPOSE 1455

# Health check (uses API_PORT env var)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import os; import httpx; httpx.get(f'http://localhost:{os.environ.get(\"API_PORT\", 1455)}/health')" || exit 1

# Use run_server.py to ensure validate_host_security is called at startup
CMD ["python", "run_server.py"]
