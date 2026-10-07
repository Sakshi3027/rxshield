"""RxShield HTTP API: authentication, request tracing, safe error mapping, and core endpoints."""
import json
from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from api.auth import TOKEN_TTL_SECONDS, AuthError, check_password, current_user, issue_token
from graph.db import get_driver
from graph.text2cypher import NotAnswerable
from observability.tracing import span
from retrieval.cache import cached_answer_for_user
from retrieval.rate_limit import RateLimited
from retrieval.tenant_rag import IDENTITY_SQL
from simulation.patient_impact import run_patient_impact
from tenancy.db import get_app_engine, user_session
from agent.shortage_memo import draft_memo
from tenancy.actions import get_action, pending_actions, review_action

load_dotenv(".env")

UNTRACED = {"/health", "/ready"}
class NotFound(Exception):
    pass


class InvalidRequest(Exception):
    pass

ERRORS = {
    AuthError: (401, "unauthorized", "Invalid credentials or token."),
    PermissionError: (403, "forbidden", "You do not have access to this resource."),
    RateLimited: (429, "rate_limited", "Too many requests. Please wait a minute and try again."),
    NotAnswerable: (422, "not_answerable", "This question cannot be answered from RxShield data."),
    NotFound: (404, "not_found", "Not found."),
    InvalidRequest: (400, "invalid_request", "This request cannot be applied."),
}
INTERNAL_ERROR = {"error": "internal_error",
                  "message": "Something went wrong. Share the trace id with support."}

app = FastAPI(title="RxShield API", version="0.1.0")


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=500)


class WhatIfRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Literal["facility", "company", "country"]
    entity: str = Field(min_length=2, max_length=20, pattern=r"^[A-Za-z0-9]+$")
    duration_days: int = Field(ge=1, le=365)

class MemoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ingredient: str = Field(min_length=2, max_length=60, pattern=r"^[A-Za-z][A-Za-z \-]*$")
    revision_of: int | None = Field(default=None, ge=1)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=1000)


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


@app.post("/ask")
def ask(body: AskRequest, user_id: str = Depends(current_user)):
    result = cached_answer_for_user(user_id, body.question)
    return {
        "answer": result["answer"],
        "cache": result["cache"],
        "trace_id": result.get("trace_id"),
        "sources": {
            "labels": [{"product": s.get("product_label"), "section": s.get("section_name")}
                       for s in result.get("label_sources", [])],
            "documents": [{"title": d.get("title"), "type": d.get("doc_type")}
                          for d in result.get("private_sources", [])],
            "inventory": result.get("inventory", []),
            "graph_rows": len(result.get("graph_rows", [])),
        },
    }


@app.post("/simulations/whatif")
def whatif(body: WhatIfRequest, user_id: str = Depends(current_user)):
    entity = body.entity.upper() if body.scope == "country" else body.entity
    impact, total_patients = run_patient_impact(user_id, body.scope, entity, body.duration_days)
    order = ["patients_at_risk", "p_stockout"] if total_patients is not None else ["p_stockout"]
    ranked = impact.sort_values(order, ascending=False)
    return {
        "scope": body.scope, "entity": entity, "duration_days": body.duration_days,
        "patients_affected": total_patients,
        "drugs": json.loads(ranked.to_json(orient="records")),
    }

@app.post("/memos", status_code=201)
def create_memo(body: MemoRequest, user_id: str = Depends(current_user)):
    try:
        state = draft_memo(user_id, body.ingredient, body.revision_of)
    except ValueError:
        raise InvalidRequest()
    if not state.get("action_id"):
        return JSONResponse({"error": "draft_failed_validation",
                             "message": "The draft did not pass validation and was not saved.",
                             "problems": state.get("problems") or []}, status_code=422)
    return {"action_id": state["action_id"], "status": "pending_approval",
            "draft": state["draft"], "attempts": state["attempts"]}


@app.get("/memos/pending")
def list_pending(user_id: str = Depends(current_user)):
    return {"memos": pending_actions(user_id)}


@app.get("/memos/{action_id}")
def read_memo(action_id: int, user_id: str = Depends(current_user)):
    with user_session(user_id) as conn:
        action = get_action(conn, action_id)
    if action is None:
        raise NotFound()
    return action


@app.post("/memos/{action_id}/review")
def review_memo(action_id: int, body: ReviewRequest, user_id: str = Depends(current_user)):
    review_action(user_id, action_id, body.decision, body.note)
    return {"action_id": action_id, "status": body.decision}