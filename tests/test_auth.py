import base64
import json
import os
import time

import jwt
from fastapi.testclient import TestClient

from api.auth import ALGORITHM, AUDIENCE, ISSUER
from api.main import app

client = TestClient(app, raise_server_exceptions=False)
USER = "northshore-pharmacist"


def login(user_id=USER, password=None):
    return client.post("/auth/login", json={"user_id": user_id,
                                            "password": password or os.environ["DEMO_PASSWORD"]})


def me(token):
    return client.get("/me", headers={"Authorization": f"Bearer {token}"})


def claims(**overrides):
    now = int(time.time())
    return {"sub": USER, "iat": now, "exp": now + 600, "iss": ISSUER, "aud": AUDIENCE, **overrides}


def test_login_then_identity_comes_from_the_token():
    response = login()
    assert response.status_code == 200
    body = me(response.json()["access_token"]).json()
    assert body["user_id"] == USER
    assert body["role"] == "pharmacist"


def test_wrong_password_and_unknown_user_look_identical():
    wrong = login(password="not-the-password")
    unknown = login(user_id="nobody-here")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_missing_token_is_rejected_with_bearer_challenge():
    response = client.get("/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_tampered_token_is_rejected():
    token = login().json()["access_token"]
    header, payload, signature = token.split(".")
    forged = json.loads(base64.urlsafe_b64decode(payload + "=="))
    forged["sub"] = "sunbelt-executive"
    forged_payload = base64.urlsafe_b64encode(json.dumps(forged).encode()).decode().rstrip("=")
    assert me(f"{header}.{forged_payload}.{signature}").status_code == 401


def test_expired_token_is_rejected():
    token = jwt.encode(claims(exp=int(time.time()) - 10), os.environ["JWT_SECRET"], algorithm=ALGORITHM)
    assert me(token).status_code == 401


def test_token_signed_with_another_secret_is_rejected():
    assert me(jwt.encode(claims(), "attacker-secret-that-is-long-enough-for-hs256", algorithm=ALGORITHM)).status_code == 401


def test_unsigned_alg_none_token_is_rejected():
    def part(data):
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")
    unsigned = f"{part({'alg': 'none', 'typ': 'JWT'})}.{part(claims())}."
    assert me(unsigned).status_code == 401