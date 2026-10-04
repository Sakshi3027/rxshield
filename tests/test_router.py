"""Routing decisions must send only pure label questions down the cheap path."""
import pytest

from retrieval.router import choose_route


@pytest.mark.parametrize("question, expected", [
    ("What are the contraindications for bupivacaine?", "label"),
    ("How should Nipent vials be stored?", "label"),
    ("What does the boxed warning for Marcaine say?", "label"),
    ("What is dexmedetomidine indicated for?", "label"),
    ("Which critical shortage drugs are made only in India?", "graph"),
    ("Which dexmedetomidine products are in shortage, and what is the drug used for?", "graph"),
    ("Where is pentostatin manufactured, and what does its boxed warning say?", "graph"),
    ("What alternatives exist for morphine?", "graph"),
    ("Which company would lose the most shortage drugs if its plants went offline?", "graph"),
])
def test_route_decisions(question, expected):
    route, _ = choose_route(question)
    assert route == expected