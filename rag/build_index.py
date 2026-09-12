"""
Offline index build for the RAG knowledge base (Phase 3, checklist 3.1).

Embedding approach: pure-Python TF-IDF, stdlib only -- no sentence-
transformers, no pretrained model to fetch. Chosen over a neural
embedding model for this checklist item because:
  - It requires nothing beyond the Python stdlib already proven present
    on this host. No pip install, no model download from PyPI/HuggingFace/
    anywhere -- so "no network calls at runtime" isn't just true, it's
    structurally guaranteed, at build time too, not only at query time.
  - This network has already shown it selectively blocks package/image
    registries (Docker Hub/GHCR confirmed blocked in Phase 0/1); HuggingFace
    Hub reachability from this host is unverified, and not worth staking
    the RAG pipeline's build step on for a 4-document placeholder corpus.
  - It matches the project's existing minimal-dependency-surface precedent
    (broker/vault_client.py is stdlib-only by design, for the same reason:
    smaller, more auditable surface on an air-gapped host).
  - TF-IDF is a real, well-understood sparse embedding technique, sufficient
    to validate the chunk -> embed -> index -> retrieve pipeline shape now.
    Swapping in a neural embedding model later is a drop-in replacement at
    the embed step only -- chunking, storage, and retrieval interface don't
    need to change.

Usage: python3 rag/build_index.py [--update]
Reads every *.md/*.txt file under rag/manuals/, chunks by paragraph,
computes an L2-normalized TF-IDF vector per chunk, and writes
rag/vector_store/index.json.

On --update (Phase 3, checklist 3.4): accepted for interface compatibility
with an "add one document without a full rebuild" workflow, but it does
NOT do a true partial update, and cannot correctly: TF-IDF's idf value
for a term is log((1+N)/(1+df(term))) + 1 -- a function of document
frequency across the *entire* corpus. Adding one new document can change
df for any term it contains, including terms that already exist in other
documents' chunks, which changes idf for those terms, which changes the
stored vector of every existing chunk that contains them (not just the
new one). Appending the new chunk's vector under the *old* idf while
leaving old vectors alone would produce vectors computed on two
different, incompatible scales in the same store -- cosine similarity
between them would be comparing apples to a different fruit, silently.
That's a correctness bug, not a performance shortcut, so --update
recomputes the full index, same as the default path. This is a real
limitation of count-based sparse embeddings specifically: a neural
embedding model (see the module docstring above) embeds each chunk
independently of the rest of the corpus, so an actual incremental
add-one-document update is possible there. At this corpus's size the
cost difference is unmeasurable anyway -- see the timing note in
project-holden-scope.md Phase 3 status.
"""

import argparse
import json
import math
import re
import sys
import time
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANUALS_DIR = REPO_ROOT / "rag" / "manuals"
VECTOR_STORE_DIR = REPO_ROOT / "rag" / "vector_store"
VECTOR_STORE_FILE = VECTOR_STORE_DIR / "index.json"

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_MIN_CHUNK_LEN = 40  # characters -- drops stray headings/blank fragments, not real content


def tokenize(text: str) -> list:
    return _TOKEN_RE.findall(text.lower())


def chunk_document(text: str, source: str) -> list:
    """Paragraph-level chunking: split on blank lines, drop short/empty fragments
    (e.g. markdown '# Heading' lines end up as their own tiny paragraph)."""
    chunks = []
    for para in re.split(r"\n\s*\n", text):
        para = re.sub(r"\s+", " ", para).strip()
        if len(para) >= _MIN_CHUNK_LEN:
            chunks.append({"source": source, "text": para})
    return chunks


def build_tfidf(chunks: list) -> dict:
    tokenized = [tokenize(c["text"]) for c in chunks]

    doc_freq = Counter()
    for tokens in tokenized:
        doc_freq.update(set(tokens))

    vocabulary = sorted(doc_freq.keys())
    vocab_index = {term: i for i, term in enumerate(vocabulary)}
    n_docs = len(chunks)
    # smoothed idf (as in scikit-learn's default): log((1+n)/(1+df)) + 1, always positive
    idf = [math.log((1 + n_docs) / (1 + doc_freq[term])) + 1.0 for term in vocabulary]

    vectors = []
    for tokens in tokenized:
        term_counts = Counter(tokens)
        vec = [0.0] * len(vocabulary)
        for term, count in term_counts.items():
            idx = vocab_index[term]
            tf = count / len(tokens)
            vec[idx] = tf * idf[idx]
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        vectors.append([v / norm for v in vec])

    return {"vocabulary": vocabulary, "idf": idf, "vectors": vectors}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--update",
        action="store_true",
        help="Accepted for an 'add a document' workflow, but performs a full recompute -- see module docstring for why a true partial update isn't valid for TF-IDF.",
    )
    args = ap.parse_args()

    if not MANUALS_DIR.is_dir():
        print(f"error: manuals directory not found: {MANUALS_DIR}", file=sys.stderr)
        return 1

    manual_files = sorted(list(MANUALS_DIR.glob("*.md")) + list(MANUALS_DIR.glob("*.txt")))
    if not manual_files:
        print(f"error: no .md/.txt files found under {MANUALS_DIR}", file=sys.stderr)
        return 1

    t0 = time.perf_counter()

    all_chunks = []
    for path in manual_files:
        all_chunks.extend(chunk_document(path.read_text(), source=str(path.relative_to(REPO_ROOT))))

    if not all_chunks:
        print("error: zero chunks produced from manuals corpus", file=sys.stderr)
        return 1

    tfidf = build_tfidf(all_chunks)

    VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
    index = {
        "embedding_method": "tfidf-v1",
        "vocabulary": tfidf["vocabulary"],
        "idf": tfidf["idf"],
        "chunks": [
            {"id": i, "source": c["source"], "text": c["text"], "vector": tfidf["vectors"][i]}
            for i, c in enumerate(all_chunks)
        ],
    }
    VECTOR_STORE_FILE.write_text(json.dumps(index, indent=2))
    elapsed_ms = (time.perf_counter() - t0) * 1000

    mode = "update (full recompute -- see --help)" if args.update else "full rebuild"
    print(
        f"[{mode}] Indexed {len(all_chunks)} chunks from {len(manual_files)} manuals "
        f"({len(tfidf['vocabulary'])} vocabulary terms) -> {VECTOR_STORE_FILE} "
        f"in {elapsed_ms:.1f}ms (index/embed work only, excludes interpreter startup)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
