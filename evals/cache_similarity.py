"""Measure whether a similarity threshold alone can separate safe cache hits from dangerous ones."""
import numpy as np

from retrieval.embed_labels import QUERY_PREFIX
from retrieval.vector_search import get_model

PAIRS = [
    ("paraphrase", "Which critical shortage drugs are made only in India?",
                   "What critical drugs in shortage are manufactured exclusively in India?"),
    ("paraphrase", "How should Nipent vials be stored?",
                   "What are the storage requirements for Nipent vials?"),
    ("paraphrase", "What are the contraindications for bupivacaine?",
                   "When should bupivacaine not be used?"),
    ("paraphrase", "How many days of lidocaine do we have?",
                   "How long will our lidocaine supply last?"),
    ("entity_swap", "Which critical shortage drugs are made only in India?",
                    "Which critical shortage drugs are made only in China?"),
    ("entity_swap", "What are the contraindications for bupivacaine?",
                    "What are the contraindications for ropivacaine?"),
    ("entity_swap", "How many days of lidocaine do we have?",
                    "How many days of morphine do we have?"),
    ("entity_swap", "Which high risk drugs are made only in India?",
                    "Which critical drugs are made only in India?"),
]


def embed(texts):
    vectors = np.array(list(get_model().embed([QUERY_PREFIX + t for t in texts])))
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def main():
    scores = {"paraphrase": [], "entity_swap": []}
    for kind, a, b in PAIRS:
        va, vb = embed([a, b])
        similarity = float(va @ vb)
        scores[kind].append(similarity)
        print(f"{similarity:.3f}  {kind:<12} {a}\n{'':19}{b}\n")

    lowest_paraphrase = min(scores["paraphrase"])
    highest_swap = max(scores["entity_swap"])
    print(f"Lowest paraphrase similarity: {lowest_paraphrase:.3f}")
    print(f"Highest entity swap similarity: {highest_swap:.3f}")
    if highest_swap >= lowest_paraphrase:
        print("No single threshold separates them. A threshold-only cache would serve wrong answers.")
    else:
        print(f"A threshold between {lowest_paraphrase:.3f} and {highest_swap:.3f} would separate these pairs.")


if __name__ == "__main__":
    main()