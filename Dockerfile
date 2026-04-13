FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-postgres.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt -r requirements-postgres.txt

COPY . .

# data papkasi SQLite uchun
RUN mkdir -p /app/data

CMD ["python", "bot.py"]
