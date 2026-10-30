FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    PDF_BROWSER_PATH=/usr/bin/chromium \
    HOME=/home/livesun

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium chromium-sandbox fonts-liberation fonts-dejavu-core ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 livesun
COPY --chown=livesun:livesun . .
RUN mkdir -p /app/storage/uploads /home/livesun/.gunicorn /home/livesun/.cache \
    && chown -R livesun:livesun /app/storage /home/livesun \
    && chmod 700 /home/livesun/.gunicorn /home/livesun/.cache
USER livesun
EXPOSE 10000
CMD ["gunicorn", "--config", "deploy/gunicorn.render.conf.py", "wsgi:app"]