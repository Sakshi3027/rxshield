"""Locust load test for the RxShield API.

Most traffic hits paths that do not call the LLM: cached answers, identity, pending memos, and the
patient-impact simulation. That measures RxShield itself without spending the Groq budget.
Run python -m loadtest.warm_cache first so every load-test user has a cached answer.
"""
import itertools

from locust import HttpUser, between, task

from loadtest.config import PASSWORD, QUESTION, USER_IDS, WHATIF

_next_user = itertools.cycle(USER_IDS)


class HospitalUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.user_id = next(_next_user)
        response = self.client.post("/auth/login", json={"user_id": self.user_id, "password": PASSWORD})
        self.headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

    @task(5)
    def cached_answer(self):
        with self.client.post("/ask", json={"question": QUESTION}, headers=self.headers,
                              name="/ask [cached]", catch_response=True) as response:
            if response.status_code == 429:
                response.failure("cache hit was rate limited")
            elif response.ok and response.json().get("cache") != "hit":
                response.failure("expected a cache hit; run python -m loadtest.warm_cache")

    @task(2)
    def identity(self):
        self.client.get("/me", headers=self.headers)

    @task(2)
    def pending_memos(self):
        self.client.get("/memos/pending", headers=self.headers)

    @task(1)
    def outage_simulation(self):
        self.client.post("/simulations/whatif", json=WHATIF, headers=self.headers)
