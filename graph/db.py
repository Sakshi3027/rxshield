"""Neo4j connection helper. Reads NEO4J_* settings from .env."""
import os

from dotenv import load_dotenv
from neo4j import GraphDatabase

load_dotenv(".env")


def get_driver():
    return GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
    )