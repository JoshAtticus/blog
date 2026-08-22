# Use Python 3.11 slim image for smaller size
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=3001

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p templates posts/assets

# Run as an unprivileged user instead of root.
# /app must be writable by appuser: the app writes blog.db (SQLite WAL) and
# creates the flask_cache directory at startup.
RUN useradd -m appuser \
    && mkdir -p /app/flask_cache \
    && chown -R appuser:appuser /app
USER appuser

# Expose port 3001
EXPOSE 3001

# Run gunicorn with 4 workers
CMD ["gunicorn", "--bind", "0.0.0.0:3001", "--workers", "4", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", "wsgi:app"]
