# Dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps for psycopg / Postgres
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt /app/
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy project
COPY . /app/

# Non-root user
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Default Django config (overridable via env)
ENV DJANGO_SETTINGS_MODULE=config.settings \
    SECRET_KEY=dummy-docker-secret \
    DEBUG=0

# Run via gunicorn (good enough for portfolio / demo)
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]