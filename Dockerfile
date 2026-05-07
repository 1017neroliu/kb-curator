FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install poetry
RUN pip install --no-cache-dir poetry

# Copy dependency files first (for caching)
COPY pyproject.toml poetry.lock* ./

# Install dependencies (no dev dependencies in production image)
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --only main

# Copy application code
COPY kb_curator/ ./kb_curator/
COPY configs/ ./configs/

# Create data directory
RUN mkdir -p /app/data

# Default command (overridden by docker-compose)
CMD ["uvicorn", "kb_curator.main:app", "--host", "0.0.0.0", "--port", "8000"]
