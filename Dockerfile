# Portable image — runs on Render, Railway, Fly.io, Koyeb, etc.
# Python 3.12 (stable prod wheels for psycopg/pydantic; avoids 3.14 edge cases).
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

# Hosts inject the port via $PORT; default to 8000 for local `docker run`.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
