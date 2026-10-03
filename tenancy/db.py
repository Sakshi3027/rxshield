"""App database access: least-privilege role, identity set per transaction, permissions decided by the database."""
import os
from contextlib import contextmanager
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy import create_engine, make_url, text

load_dotenv(".env")


@lru_cache(maxsize=1)
def get_app_engine():
    admin_url = make_url(os.environ["DATABASE_URL"])
    project_ref = admin_url.username.split(".", 1)[1]
    app_url = admin_url.set(
        drivername="postgresql+psycopg",
        username=f"rxshield_app.{project_ref}",
        password=os.environ["APP_DB_PASSWORD"],
    )
    return create_engine(app_url, pool_pre_ping=True, hide_parameters=True)

@contextmanager
def user_session(user_id):
    with get_app_engine().begin() as conn:
        conn.execute(text("select set_config('app.user_id', :u, true)"), {"u": user_id})
        yield conn