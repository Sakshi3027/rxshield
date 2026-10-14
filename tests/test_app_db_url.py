"""The deployed API must connect as the app role without ever needing the admin URL."""
from tenancy.db import app_database_url


def test_explicit_app_url_wins_and_needs_no_admin_url(monkeypatch):
    monkeypatch.setenv("APP_DATABASE_URL", "postgresql://rxshield_app.abc:secret@db.example.com:6543/postgres")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    url = app_database_url()
    assert (url.username, url.host, url.drivername) == ("rxshield_app.abc", "db.example.com", "postgresql+psycopg")


def test_local_derives_app_url_from_admin_url(monkeypatch):
    monkeypatch.delenv("APP_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres.abc:adminpw@db.example.com:6543/postgres")
    monkeypatch.setenv("APP_DB_PASSWORD", "apppw")
    url = app_database_url()
    assert url.username == "rxshield_app.abc"
    password_matches = url.password == "apppw"
    assert password_matches
