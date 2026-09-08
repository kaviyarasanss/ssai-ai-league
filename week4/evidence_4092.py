"""
EVIDENCE: the ERR-4092 failure, chunk by chunk and rank by rank.

Answers exactly:
  1. Which chunk(s) contain the literal string 'ERR-4092'?
  2. What rank did that chunk get under each retrieval strategy?
  3. At what depth (top-K) would it have been retrieved?

Zero API calls.
Run:  python week4/evidence_4092.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from week3 import rag
from week4 import retrieval

QUESTION = "What does ERR-4092 mean?"
NEEDLE = "ERR-4092"

print("Building index (chunk_size=600, overlap=100)...")
chunks = rag.build_chunks(chunk_size=600, overlap=100)
matrix = rag.embed_chunks(chunks)
bm25 = retrieval.build_bm25(chunks)
print(f"{len(chunks)} chunks total\n")

# ----------------------------------------------------------------------
print("=" * 78)
print(f"1. WHICH CHUNKS CONTAIN THE LITERAL STRING {NEEDLE!r}?")
print("=" * 78)
holders = [i for i, c in enumerate(chunks) if NEEDLE in c["text"]]
if not holders:
    print("  NONE - the string does not exist in any chunk.")
for i in holders:
    c = chunks[i]
    print(f"\n  chunk index {i}   id={c['chunk_id']}")
    print(f"  file    : {c['doc_id']}")
    print(f"  section : {c['section']}")
    print(f"  length  : {len(c['text'])} chars")
    print("  --- full text ---")
    for line in c["text"].splitlines():
        print(f"    {line}")

# ----------------------------------------------------------------------
print()
print("=" * 78)
print("2. WHERE DOES THAT CHUNK RANK UNDER EACH STRATEGY?")
print("=" * 78)


def full_ranking_dense():
    q = rag.get_encoder().encode(QUESTION, normalize_embeddings=True)
    scores = matrix @ q
    order = np.argsort(scores)[::-1]
    return [(int(i), float(scores[i])) for i in order]


def full_ranking_bm25():
    scores = bm25.get_scores(retrieval.tokenize(QUESTION))
    order = np.argsort(scores)[::-1]
    return [(int(i), float(scores[i])) for i in order]


by_id = {c["chunk_id"]: i for i, c in enumerate(chunks)}


def ranking_hybrid():
    fused = retrieval.hybrid_search(QUESTION, chunks, matrix, bm25,
                                    rag.search, k=len(chunks), pool=len(chunks))
    return [(by_id[c["chunk_id"]], c["score"]) for c in fused]


def ranking_rerank_of_dense12():
    cands = rag.search(QUESTION, chunks, matrix, k=12)
    out = retrieval.rerank(QUESTION, cands, k=12)
    return [(by_id[c["chunk_id"]], c["score"]) for c in out]


strategies = {
    "DENSE (week 3 + week 4 baseline)": full_ranking_dense(),
    "BM25 keyword only":                full_ranking_bm25(),
    "HYBRID dense+bm25 RRF":            ranking_hybrid(),
    "DENSE top-12 then RERANK":         ranking_rerank_of_dense12(),
}

for name, ranking in strategies.items():
    print(f"\n  --- {name} ---")
    pos = {idx: r for r, (idx, _) in enumerate(ranking, start=1)}
    for i in holders:
        r = pos.get(i)
        if r is None:
            print(f"    chunk {i} ({chunks[i]['doc_id']}): NOT IN THIS RANKING")
        else:
            score = dict((a, b) for a, b in ranking)[i]
            verdict = ("RETRIEVED at top-3" if r <= 3 else
                       "in top-12 pool but NOT top-3" if r <= 12 else
                       "MISSED - outside top-12")
            print(f"    chunk {i} ({chunks[i]['doc_id']} > {chunks[i]['section']})")
            print(f"       rank {r} of {len(ranking)}   score {score:.4f}   -> {verdict}")
    print("    top 5 actually returned:")
    for r, (idx, sc) in enumerate(ranking[:5], start=1):
        mark = "  <== THE ERR-4092 CHUNK" if idx in holders else ""
        print(f"       {r}. {sc:>8.4f}  {chunks[idx]['doc_id']:<26} > "
              f"{chunks[idx]['section']}{mark}")

# ----------------------------------------------------------------------
print()
print("=" * 78)
print("3. WHAT TOP-K WOULD HAVE BEEN NEEDED?")
print("=" * 78)
for name, ranking in strategies.items():
    pos = {idx: r for r, (idx, _) in enumerate(ranking, start=1)}
    need = min((pos[i] for i in holders if i in pos), default=None)
    print(f"  {name:<36} k >= {need}" if need else f"  {name:<36} never")
