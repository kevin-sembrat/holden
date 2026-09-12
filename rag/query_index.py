"""
Retrieval for the RAG knowledge base (Phase 3, checklist 3.2).

Embeds a query string with the exact same vocabulary/idf that
rag/build_index.py computed at index-build time (out-of-vocabulary query
terms are dropped, not hashed/approximated -- a query sharing zero
vocabulary with the corpus is a real, informative failure case, not
something to paper over), then ranks stored chunks by cosine similarity.
Since both the stored chunk vectors and the query vector are L2-normalized,
cosine similarity is just their dot product.
"""

import argparse
import json
import math
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VECTOR_STORE_FILE = REPO_ROOT / "rag" / "vector_store" / "index.json"

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list:
    return _TOKEN_RE.findall(text.lower())


def load_index(path: Path = VECTOR_STORE_FILE) -> dict:
    return json.loads(path.read_text())


def embed_query(query: str, index: dict) -> list:
    """Same tf-idf formula build_index.py used per chunk, applied to the query,
    using the corpus's existing vocabulary/idf -- not refit."""
    vocab_index = {term: i for i, term in enumerate(index["vocabulary"])}
    idf = index["idf"]
    tokens = tokenize(query)

    vec = [0.0] * len(index["vocabulary"])
    if not tokens:
        return vec

    from collections import Counter

    term_counts = Counter(tokens)
    for term, count in term_counts.items():
        idx = vocab_index.get(term)
        if idx is not None:
            tf = count / len(tokens)
            vec[idx] = tf * idf[idx]

    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine_similarity(a: list, b: list) -> float:
    return sum(x * y for x, y in zip(a, b))


def search(query: str, top_k: int = 5, index: dict = None) -> list:
    index = load_index() if index is None else index
    query_vec = embed_query(query, index)

    scored = [
        {
            "id": chunk["id"],
            "source": chunk["source"],
            "text": chunk["text"],
            "score": cosine_similarity(query_vec, chunk["vector"]),
        }
        for chunk in index["chunks"]
    ]
    scored.sort(key=lambda r: r["score"], reverse=True)
    return scored[:top_k]


def main() -> int:
    ap = argparse.ArgumentParser(description="Query the RAG vector store for the top-k most similar chunks.")
    ap.add_argument("query", help="Query string")
    ap.add_argument("--top-k", type=int, default=5)
    args = ap.parse_args()

    if not VECTOR_STORE_FILE.exists():
        print(json.dumps({"error": f"vector store not found at {VECTOR_STORE_FILE} -- run rag/build_index.py first"}, indent=2))
        return 2

    results = search(args.query, top_k=args.top_k)
    print(json.dumps({"query": args.query, "results": results}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
