"""
Retrieval accuracy eval (Phase 3, checklist 3.2).

Runs every labeled query in rag/eval/labeled_queries.json through
rag/query_index.py's search(), and reports whether each query's expected
chunk id appears in the top-k results. Not a pass/fail gate on CI (there
isn't one yet) -- a repeatable way to re-check retrieval accuracy any
time the manuals corpus, chunking, or embedding approach changes.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from query_index import search, load_index  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LABELED_QUERIES_FILE = Path(__file__).resolve().parent / "labeled_queries.json"


def main() -> int:
    labeled = json.loads(LABELED_QUERIES_FILE.read_text())["queries"]
    index = load_index()

    n_pass = 0
    for q in labeled:
        results = search(q["query"], top_k=5, index=index)
        found_ids = [r["id"] for r in results]
        passed = q["expected_chunk_id"] in found_ids
        n_pass += passed

        print(f"[{q['id']}] ({q['difficulty']}) {'PASS' if passed else 'FAIL'}")
        print(f"  query: {q['query']}")
        print(f"  expected: chunk {q['expected_chunk_id']} ({q['expected_source']})")
        for r in results:
            marker = " <-- expected" if r["id"] == q["expected_chunk_id"] else ""
            print(f"    id={r['id']:2d}  score={r['score']:.4f}  {r['source']}{marker}")
        print()

    print(f"{n_pass}/{len(labeled)} queries retrieved their expected chunk in the top 5.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
