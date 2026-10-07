"""Give every seeded user a bcrypt-hashed demo password. Admin connection; run after tenancy.setup."""
import os

import bcrypt
from dotenv import load_dotenv
from sqlalchemy import text

from ingestion.db import get_engine

load_dotenv(".env")


def main():
    password = os.environ["DEMO_PASSWORD"].encode()
    with get_engine().begin() as conn:
        users = conn.execute(text("select user_id from tenancy.users order by user_id")).scalars().all()
        for user_id in users:
            hashed = bcrypt.hashpw(password, bcrypt.gensalt()).decode()
            conn.execute(text("""
                insert into tenancy.credentials (user_id, password_hash) values (:u, :h)
                on conflict (user_id) do update set password_hash = excluded.password_hash, updated_at = now()"""),
                {"u": user_id, "h": hashed})
    print(f"Set demo credentials for {len(users)} users")


if __name__ == "__main__":
    main()