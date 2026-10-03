"""App database access: least-privilege role with the tenant set per transaction."""
import os
from contextlib import contextmanager
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(".env")


@lru_cache(maxsize=1)
def get_app_engine():
    url = os.environ["APP_DATABASE_URL"].replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(url, pool_pre_ping=True)


@contextmanager
def tenant_session(tenant_id):
    with get_app_engine().begin() as conn:
        conn.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": tenant_id})
        yield conn