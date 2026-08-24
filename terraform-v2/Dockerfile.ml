# =============================================================================
# Dockerfile for ML Inference Service
# Dedicated service for machine learning model inference and predictions
# =============================================================================

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    g++ \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy Docker-compatible requirements (base + langchain)
COPY requirements-docker.txt requirements.txt

# Install Python dependencies (including ML libraries)
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ./app ./app
COPY ./ML_Complete_Package ./ML_Complete_Package
COPY ./post_care ./post_care
COPY .env.example .env

# Create directories for model cache
RUN mkdir -p /models /app/logs

# Create non-root user
RUN useradd -m -u 1000 mluser && chown -R mluser:mluser /app /models
USER mluser

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Start ML service application
CMD ["uvicorn", "app.ml_service:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
