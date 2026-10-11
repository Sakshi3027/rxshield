"""The MCP server must log in, send the bearer token, re-login once on expiry, and surface API errors."""
import json

import httpx
import pytest

from rxshield_mcp.server import RxShieldClient, RxShieldError


def make_client(handler):
    return RxShieldClient("http://api.test", "northshore-pharmacist", "pw", transport=httpx.MockTransport(handler))


def test_logs_in_and_sends_bearer_token():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={"access_token": "tok1", "token_type": "bearer"})
        return httpx.Response(200, json={"answer": "ok"})

    assert make_client(handler).request("POST", "/ask", {"question": "heparin days?"}) == {"answer": "ok"}
    assert json.loads(seen[0].content) == {"user_id": "northshore-pharmacist", "password": "pw"}
    assert seen[1].headers["Authorization"] == "Bearer tok1"
    assert json.loads(seen[1].content) == {"question": "heparin days?"}


def test_expired_token_logs_in_again_once():
    tokens = iter(["old", "new"])
    calls = []

    def handler(request):
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={"access_token": next(tokens)})
        calls.append(request.headers["Authorization"])
        return httpx.Response(401 if len(calls) == 1 else 200, json={})

    make_client(handler).request("GET", "/memos/pending")
    assert calls == ["Bearer old", "Bearer new"]


def test_api_error_message_is_surfaced():
    def handler(request):
        if request.url.path == "/auth/login":
            return httpx.Response(200, json={"access_token": "t"})
        return httpx.Response(403, json={"error": {"code": "forbidden", "message": "You do not have access to this resource."}})

    with pytest.raises(RxShieldError, match="do not have access"):
        make_client(handler).request("GET", "/memos/pending")


def test_bad_password_fails_clearly():
    def handler(request):
        return httpx.Response(401, json={"error": {"code": "unauthorized", "message": "Invalid credentials or token."}})

    with pytest.raises(RxShieldError, match="Login failed"):
        make_client(handler).request("GET", "/memos/pending")


def test_unreachable_api_gives_clear_error():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(RxShieldError, match="unreachable"):
        make_client(handler).request("GET", "/memos/pending")


def test_errors_are_mcp_tool_errors_so_messages_reach_the_client():
    from mcp.server.mcpserver.exceptions import ToolError
    assert issubclass(RxShieldError, ToolError)
