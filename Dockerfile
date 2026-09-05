# syntax=docker/dockerfile:1

FROM python:3.13-slim AS builder

WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.13-slim AS runtime

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appsvc \
    && mkdir -p /app \
    && chown -R appsvc:appsvc /app

COPY --from=builder /install /usr/local
COPY --chown=appsvc:appsvc src/ /app/src/

WORKDIR /app
USER appsvc

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=local \
    LOG_LEVEL=INFO \
    WORKERS=1 \
    MAX_CONNECTIONS=100 \
    REDIS_HOST=127.0.0.1 \
    REDIS_PORT=6379
# REDIS_PASSWORD must be supplied at runtime (.env / Secret) — never baked into the image.

EXPOSE 8080

# WORKERS is an app config signal; container process uses a single uvicorn worker
# so Kubernetes HPA owns horizontal scale. Raise --workers only for VM installs.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
