"""Authentication: bcrypt password checks and short-lived signed tokens."""
import os
import time
from functools import lru_cache

import bcrypt
import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text

from tenancy.db import get_app_engine

TOKEN_TTL_SECONDS = 3600
ISSUER = "rxshield"
AUDIENCE = "rxshield-api"
ALGORITHM = "HS256"
BCRYPT_MAX_BYTES = 72
DUMMY_HASH = bcrypt.hashpw(b"timing-equalizer", bcrypt.gensalt())


class AuthError(Exception):
    pass


@lru_cache(maxsize=1)
def _engine():
    return get_app_engine()


def check_password(user_id, password):
    candidate = password.encode()
    if len(candidate) > BCRYPT_MAX_BYTES:
        return False
    with _engine().connect() as conn:
        stored = conn.execute(text("select tenancy.password_hash(:u)"), {"u": user_id}).scalar()
    matches = bcrypt.checkpw(candidate, stored.encode() if stored else DUMMY_HASH)
    return stored is not None and matches


def issue_token(user_id):
    now = int(time.time())
    claims = {"sub": user_id, "iat": now, "exp": now + TOKEN_TTL_SECONDS, "iss": ISSUER, "aud": AUDIENCE}
    return jwt.encode(claims, os.environ["JWT_SECRET"], algorithm=ALGORITHM)


def verify_token(token):
    try:
        claims = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[ALGORITHM],
                            audience=AUDIENCE, issuer=ISSUER,
                            options={"require": ["sub", "exp", "iat", "iss", "aud"]})
    except jwt.InvalidTokenError:
        raise AuthError()
    return claims["sub"]


bearer = HTTPBearer(auto_error=False)


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if credentials is None:
        raise AuthError()
    return verify_token(credentials.credentials)