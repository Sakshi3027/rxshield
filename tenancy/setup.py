"""Create the tenancy schema, the least-privilege app role, row-level security, and seed tenants and users."""
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

from ingestion.db import get_engine

load_dotenv(".env")

APP_ROLE = "rxshield_app"
SCHEMA_SQL = Path("tenancy/schema.sql")
TENANTS = [
    ("northshore", "Northshore Health System", "New England"),
    ("greatlakes", "Great Lakes Medical Group", "Midwest"),
    ("sunbelt", "Sunbelt Community Hospitals", "Southeast"),
]
ROLES = ["pharmacist", "procurement", "clinician", "executive"]


def main():
    password = os.environ["APP_DB_PASSWORD"]
    if not re.fullmatch(r"[A-Za-z0-9]{16,}", password):
        raise ValueError("APP_DB_PASSWORD must be at least 16 letters and digits.")

    engine = get_engine()
    with engine.begin() as conn:
        exists = conn.execute(text("select 1 from pg_roles where rolname = :r"), {"r": APP_ROLE}).scalar()
        verb = "alter" if exists else "create"
        conn.execute(text(f"{verb} role {APP_ROLE} with login nobypassrls password '{password}'"))
        conn.execute(text(SCHEMA_SQL.read_text()))

        for tenant_id, name, region in TENANTS:
            conn.execute(text(
                "insert into tenancy.tenants (tenant_id, name, region) values (:t, :n, :r) "
                "on conflict (tenant_id) do nothing"), {"t": tenant_id, "n": name, "r": region})
            for role in ROLES:
                conn.execute(text(
                    "insert into tenancy.users (user_id, tenant_id, display_name, role) "
                    "values (:u, :t, :d, :r) on conflict (user_id) do nothing"),
                    {"u": f"{tenant_id}-{role}", "t": tenant_id,
                     "d": f"{name.split()[0]} {role.title()}", "r": role})

        users = conn.execute(text("select count(*) from tenancy.users")).scalar()
        print(f"Role {APP_ROLE} {'updated' if exists else 'created'}, schema applied, {len(TENANTS)} tenants and {users} users seeded")


if __name__ == "__main__":
    main()