"""data-sync sample FastAPI service.

Contract fixture for Helm/Ansible: env-driven config, /health, /metrics, Redis.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from dotenv import load_dotenv
import redis.asyncio as redis
from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest

# Local/dev: load task-0-sample-app/.env (never commit secrets).
# In Kubernetes/Compose, env vars are injected and override file values.
load_dotenv()

REQUESTS_TOTAL = Counter(
    "data_sync_http_requests_total",
    "Total HTTP requests handled by data-sync",
    ["path", "method", "status"],
)
REDIS_UP = Gauge(
    "data_sync_redis_up",
    "1 if Redis PING succeeded on last check, else 0",
)


def _env(name: str, default: Optional[str] = None) -> str:
    value = os.getenv(name, default)
    if value is None or value == "":
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def _build_redis_client() -> redis.Redis:
    max_connections = int(os.getenv("MAX_CONNECTIONS", "100"))
    return redis.Redis(
        host=_env("REDIS_HOST", "127.0.0.1"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        password=_env("REDIS_PASSWORD"),
        max_connections=max_connections,
        decode_responses=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    log_level = os.getenv("LOG_LEVEL", "INFO")
    _configure_logging(log_level)
    logger = logging.getLogger("data-sync")

    app.state.app_env = os.getenv("APP_ENV", "local")
    app.state.workers = int(os.getenv("WORKERS", "4"))
    app.state.redis = _build_redis_client()

    logger.info(
        "starting data-sync env=%s workers=%s redis=%s:%s auth=password",
        app.state.app_env,
        app.state.workers,
        os.getenv("REDIS_HOST", "127.0.0.1"),
        os.getenv("REDIS_PORT", "6379"),
    )
    yield
    await app.state.redis.aclose()
    logger.info("shutdown complete")


app = FastAPI(title="data-sync", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def metrics_middleware(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path not in ("/metrics",):
        REQUESTS_TOTAL.labels(
            path=path,
            method=request.method,
            status=str(response.status_code),
        ).inc()
    return response


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness/readiness probe — keep cheap (no Redis dependency)."""
    return {"status": "ok"}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/cache/ping")
async def cache_ping() -> dict[str, str]:
    """Smoke endpoint to verify Redis connectivity and AUTH."""
    try:
        pong = await app.state.redis.ping()
        REDIS_UP.set(1 if pong else 0)
        return {"redis": "ok" if pong else "failed"}
    except Exception as exc:  # noqa: BLE001 — surface failure for smoke tests
        REDIS_UP.set(0)
        logging.getLogger("data-sync").warning("redis ping failed: %s", exc)
        return {"redis": "error", "detail": str(exc)}
