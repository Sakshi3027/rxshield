"""MCP server that exposes RxShield as tools for AI clients such as Claude Desktop.

It is a thin client of the RxShield API: it signs in as a configured user and calls the
same endpoints the web app uses, so login, roles, tenant isolation, rate limits, and
tracing all still apply. There is deliberately no review tool: approving or rejecting
a memo stays a human action in the web app.
"""
import os
from pathlib import Path
from typing import Literal

import httpx
from dotenv import load_dotenv
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

load_dotenv(Path(__file__).resolve().parents[1] / ".env")



class RxShieldError(ToolError):
    """A readable error for the AI client. ToolError messages are passed through by the MCP SDK; other exceptions are masked."""


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.reason_phrase
    if isinstance(body, dict):
        inner = body.get("error")
        if isinstance(inner, dict) and isinstance(inner.get("message"), str):
            return inner["message"]
        if isinstance(body.get("message"), str):
            return body["message"]
    return response.reason_phrase


class RxShieldClient:
    def __init__(self, base_url: str, user_id: str, password: str, transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(base_url=base_url, timeout=120, transport=transport)
        self._user_id = user_id
        self._password = password
        self._token: str | None = None

    def _call(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            return self._http.request(method, path, **kwargs)
        except httpx.TransportError:
            raise RxShieldError("The RxShield API is unreachable. Check that it is running.") from None

    def _login(self) -> None:
        response = self._call("POST", "/auth/login", json={"user_id": self._user_id, "password": self._password})
        if response.status_code != 200:
            raise RxShieldError(f"Login failed: {_error_message(response)}")
        self._token = response.json()["access_token"]

    def _send(self, method: str, path: str, body: dict | None) -> httpx.Response:
        return self._call(method, path, json=body, headers={"Authorization": f"Bearer {self._token}"})

    def request(self, method: str, path: str, body: dict | None = None) -> dict:
        if self._token is None:
            self._login()
        response = self._send(method, path, body)
        if response.status_code == 401:
            self._login()
            response = self._send(method, path, body)
        if response.is_error:
            raise RxShieldError(f"{_error_message(response)} (HTTP {response.status_code})")
        return response.json()


_client: RxShieldClient | None = None


def client() -> RxShieldClient:
    global _client
    if _client is None:
        user_id = os.environ.get("RXSHIELD_MCP_USER")
        password = os.environ.get("RXSHIELD_MCP_PASSWORD")
        if not user_id or not password:
            raise RxShieldError("Set RXSHIELD_MCP_USER and RXSHIELD_MCP_PASSWORD for the RxShield MCP server.")
        _client = RxShieldClient(os.environ.get("RXSHIELD_API_URL", "http://127.0.0.1:8000"), user_id, password)
    return _client


mcp = MCPServer("RxShield")


@mcp.tool()
def ask(question: str) -> dict:
    """Answer a drug shortage question with citations.

    Uses public FDA shortage, label, and manufacturing data, plus the hospital's own inventory
    and protocols when the signed-in role is allowed to see them. Citation markers in the answer:
    [G] shortage graph, [L1] FDA label, [H] hospital inventory, [P1] hospital document.
    """
    return client().request("POST", "/ask", {"question": question})


@mcp.tool()
def simulate_outage(scope: Literal["facility", "company", "country"], entity: str, duration_days: int = 30) -> dict:
    """Estimate which of the hospital's drugs and patients are at risk if a supplier goes offline.

    scope is facility, company, or country. entity is the identifier RxShield uses, letters and
    digits only, for example a two-letter country code such as IN or CN. duration_days is 1 to 365.
    """
    return client().request(
        "POST", "/simulations/whatif", {"scope": scope, "entity": entity, "duration_days": duration_days}
    )


@mcp.tool()
def draft_memo(ingredient: str) -> dict:
    """Draft a shortage response memo for one ingredient, for example lidocaine.

    The memo is saved as pending approval. An executive who did not draft it must approve
    or reject it in the RxShield web app; this tool cannot approve anything.
    """
    return client().request("POST", "/memos", {"ingredient": ingredient})


@mcp.tool()
def list_pending_memos() -> dict:
    """List shortage memos waiting for executive review at the signed-in user's hospital."""
    return client().request("GET", "/memos/pending")


@mcp.tool()
def get_memo(memo_id: int) -> dict:
    """Read one shortage memo, including its status and any reviewer note."""
    return client().request("GET", f"/memos/{memo_id}")


if __name__ == "__main__":
    mcp.run()
