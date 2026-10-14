"""Shared settings for the load test and the cache warm-up."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

PASSWORD = os.environ.get("DEMO_PASSWORD", "")
TENANTS = ("greatlakes", "northshore", "riverbend", "sunbelt")
ROLES = ("pharmacist", "procurement", "executive")  # clinicians cannot see inventory, which the simulation needs
USER_IDS = [f"{tenant}-{role}" for role in ROLES for tenant in TENANTS]
QUESTION = "How should Nipent (pentostatin) vials be stored?"
WHATIF = {"scope": "country", "entity": "IN", "duration_days": 30}
