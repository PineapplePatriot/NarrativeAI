# NarrativeAI on a server (Railway or any Docker host). See docs/DEPLOY.md.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# ffmpeg: joining voice clips (pydub)
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

WORKDIR /app/narrative
RUN DJANGO_DEBUG=0 python manage.py collectstatic --noinput

# The database, chats and uploads live on the persistent disk mounted at NARRATIVE_DATA_DIR (/data).
# One worker (SQLite likes a single writer) with threads, so streamed replies don't block each other.
CMD ["sh", "-c", "python manage.py migrate --noinput && (python manage.py seed_demo || true) && gunicorn narrative.wsgi --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 8 --timeout 300"]
