"""Neo4j connection helper: one long-lived, thread-safe driver per process."""
import os
from contextlib import contextmanager
from functools import lru_cache

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(".env")


@lru_cache(maxsize=1)
def shared_driver():
    return GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
        liveness_check_timeout=30,
    )


@contextmanager
def get_driver():
    yield shared_driver()


def close_driver():
    if shared_driver.cache_info().currsize:
        shared_driver().close()
        shared_driver.cache_clear()