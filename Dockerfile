FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# System deps for psycopg etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
  && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements-prod.txt .
RUN pip install --upgrade pip && pip install -r requirements-prod.txt

# Copy app
COPY . .
RUN chmod +x /app/docker-entrypoint.sh

ENV DJANGO_SETTINGS_MODULE=config.settings
ENV SECRET_KEY=dummy-docker-secret
ENV DEBUG=0

# Default DB/Redis URLs for docker-compose
ENV DATABASE_URL=postgres://app:app@postgres:5432/app
ENV REDIS_URL=redis://redis:6379/0

# Optional: don't fail if collectstatic not fully configured
RUN python manage.py collectstatic --noinput || true

# JSON exec-form does not expand $PORT; use sh -c. Default 8000 when PORT is unset.
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["sh", "-c", "exec python -m gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000}"]