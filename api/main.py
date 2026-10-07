"""RxShield HTTP API: request tracing, safe error mapping, health and readiness."""
from functools import lru_cache

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from graph.db import get_driver
from graph.text2cypher import NotAnswerable
from observability.tracing import span
from retrieval.rate_limit import RateLimited
from tenancy.db import get_app_engine

UNTRACED = {"/health", "/ready"}
ERRORS = {
    PermissionError: (403, "forbidden", "You do not have access to this resource."),
    RateLimited: (429, "rate_limited", "Too many requests. Please wait a minute and try again."),
    NotAnswerable: (422, "not_answerable", "This question cannot be answered from RxShield data."),
}
INTERNAL_ERROR = {"error": "internal_error",
                  "message": "Something went wrong. Share the trace id with support."}

app = FastAPI(title="RxShield API", version="0.1.0")


@lru_cache(maxsize=1)
def app_engine():
    return get_app_engine()


def error_handler(status, code, message):
    async def handle(request: Request, exc: Exception):
        return JSONResponse({"error": code, "message": message}, status_code=status)
    return handle


for exc_class, (status, code, message) in ERRORS.items():
    app.add_exception_handler(exc_class, error_handler(status, code, message))


@app.middleware("http")
async def trace_requests(request: Request, call_next):
    if request.url.path in UNTRACED:
        return await call_next(request)
    try:
        with span("http", method=request.method, path=request.url.path) as current:
            response = await call_next(request)
            current.attributes["status"] = response.status_code
    except Exception:
        response = JSONResponse(INTERNAL_ERROR, status_code=500)
    response.headers["X-Trace-Id"] = current.trace_id
    return response


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    checks = {}
    try:
        with app_engine().connect() as conn:
            conn.execute(text("select 1"))
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = type(exc).__name__
    try:
        with get_driver() as driver:
            driver.verify_connectivity()
        checks["neo4j"] = "ok"
    except Exception as exc:
        checks["neo4j"] = type(exc).__name__
    healthy = all(value == "ok" for value in checks.values())
    return JSONResponse({"status": "ready" if healthy else "degraded", "checks": checks},
                        status_code=200 if healthy else 503)