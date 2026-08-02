FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORTPULSE_DATA_DIR=/data

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Seed and train at build time so the container starts instantly and needs no
# network at run time.
RUN mkdir -p /data && python -m app.seed --force \
 && python -c "from app.db import session_scope; from app.services.forecast import get_bundle; \
    db = session_scope().__enter__(); get_bundle(db)"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
