"""Ask the load-test question once per load-test user, slowly, so every tenant and role has a cached answer."""
import sys
import time

import httpx

from loadtest.config import PASSWORD, QUESTION, USER_IDS


def main(base_url: str = "http://127.0.0.1:8000") -> None:
    with httpx.Client(base_url=base_url, timeout=120) as http:
        for user_id in USER_IDS:
            token = http.post("/auth/login", json={"user_id": user_id, "password": PASSWORD}).json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            for _ in range(3):
                response = http.post("/ask", json={"question": QUESTION}, headers=headers)
                if response.status_code != 503:
                    break
                time.sleep(20)
            cache = response.json().get("cache") if response.is_success else "-"
            print(f"{user_id:24} HTTP {response.status_code}  cache={cache}")
            time.sleep(8)


if __name__ == "__main__":
    main(*sys.argv[1:])
