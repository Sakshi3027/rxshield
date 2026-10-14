"""App database access: least-privilege role, identity set per transaction, permissions decided by the database."""
import os
from contextlib import contextmanager
from functools import lru_cache

from dotenv import load_dotenv
from sqlalchemy import create_engine, make_url, text

load_dotenv(".env")


def app_database_url():
    """The app role's connection URL.

    Deployed: read APP_DATABASE_URL, so the server never holds admin credentials.
    Local: derive it from the admin DATABASE_URL by swapping in the app role and its password.
    """
    explicit = os.environ.get("APP_DATABASE_URL")
    if explicit:
        return make_url(explicit).set(drivername="postgresql+psycopg")
    admin_url = make_url(os.environ["DATABASE_URL"])
    project_ref = admin_url.username.split(".", 1)[1]
    return admin_url.set(
        drivername="postgresql+psycopg",
        username=f"rxshield_app.{project_ref}",
        password=os.environ["APP_DB_PASSWORD"],
    )


@lru_cache(maxsize=1)
def get_app_engine():
    return create_engine(app_database_url(), pool_pre_ping=True, hide_parameters=True)

@contextmanager
def user_session(user_id):
    with get_app_engine().begin() as conn:
        conn.execute(text("select set_config('app.user_id', :u, true)"), {"u": user_id})
        yield conn