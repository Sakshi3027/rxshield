"""RxShield HTTP API: authentication, request tracing, safe error mapping, health and readiness."""
from functools import lru_cache

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.auth import TOKEN_TTL_SECONDS, AuthError, check_password, current_user, issue_token
from graph.db import get_driver
from graph.text2cypher import NotAnswerable
from observability.tracing import span
from retrieval.rate_limit import RateLimited
from retrieval.tenant_rag import IDENTITY_SQL
from tenancy.db import get_app_engine, user_session

load_dotenv(".env")

UNTRACED = {"/health", "/ready"}
ERRORS = {
    AuthError: (401, "unauthorized", "Invalid credentials or token."),
    PermissionError: (403, "forbidden", "You do not have access to this resource."),
    RateLimited: (429, "rate_limited", "Too many requests. Please wait a minute and try again."),
    NotAnswerable: (422, "not_answerable", "This question cannot be answered from RxShield data."),
}
INTERNAL_ERROR = {"error": "internal_error",
                  "message": "Something went wrong. Share the trace id with support."}

app = FastAPI(title="RxShield API", version="0.1.0")


class LoginRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


@lru_cache(maxsize=1)
def app_engine():
    return get_app_engine()


def error_handler(status, code, message):
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None

    async def handle(request: Request, exc: Exception):
        return JSONResponse({"error": code, "message": message}, status_code=status, headers=headers)
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


@app.post("/auth/login")
def login(body: LoginRequest):
    if not check_password(body.user_id, body.password):
        raise AuthError()
    return {"access_token": issue_token(body.user_id), "token_type": "bearer",
            "expires_in": TOKEN_TTL_SECONDS}


@app.get("/me")
def me(user_id: str = Depends(current_user)):
    with user_session(user_id) as conn:
        identity = conn.execute(text(IDENTITY_SQL)).mappings().one_or_none()
    if identity is None:
        raise PermissionError()
    return {"user_id": user_id, **identity}