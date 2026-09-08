"""
WEEK 4 - Better retrieval: keyword search, hybrid fusion, reranking.

Week 3 used ONE retrieval method: dense (vector) search.
Week 1 showed its weakness measured directly - ERR-4032 vs ERR-4033 scored
0.970 similar. The embedding knows "this is an error code", not which one.

This module adds:
  1. BM25   - classic keyword search. Treats ERR-4032 and ERR-4033 as
              completely different strings. Strong exactly where dense is weak.
  2. Hybrid - run both, fuse the two ranked lists with RRF.
  3. Rerank - a cross-encoder re-scores the shortlist by reading the question
              and the chunk TOGETHER.

None of this costs an API call.
"""
import re
import numpy as np
from rank_bm25 import BM25Okapi


# ======================================================================
# 1. BM25 - SPARSE / KEYWORD RETRIEVAL
#
# BM25 scores a document by how many of the query's words it contains,
# weighted so that:
#   - rare words count for more than common ones (a doc containing
#     "ERR-4032" is far more informative than one containing "the")
#   - repeating a word gives diminishing returns
#   - long documents are penalised so they cannot win just by being long
#
# It has NO idea what words mean. "refund" and "money back" are unrelated
# to BM25. That is exactly why it complements dense search.
# ======================================================================
def tokenize(text: str) -> list[str]:
    """
    Lowercase and split into words, KEEPING hyphenated identifiers intact
    and also emitting their parts.

    'ERR-4032' -> ['err-4032', 'err', '4032']

    Keeping the whole token lets an exact match score highly; also emitting
    the parts means 'ERR 4032' typed with a space still matches.
    """
    text = text.lower()
    tokens = re.findall(r"[a-z0-9][a-z0-9_\-\.]*", text)
    out = []
    for t in tokens:
        # Strip trailing punctuation. Without this, "ERR-4092." in a sentence
        # tokenises as 'err-4092.' and never matches the query's 'err-4092'.
        # That one character silently broke exact-code matching.
        t = t.rstrip(".-_")
        if not t:
            continue
        out.append(t)
        if "-" in t or "_" in t:
            out.extend(part for part in re.split(r"[-_.]", t) if part)
    return out


def build_bm25(chunks: list[dict]) -> BM25Okapi:
    corpus = [tokenize(f"{c['title']} {c['section']} {c['text']}") for c in chunks]
    return BM25Okapi(corpus)


def bm25_search(question: str, chunks: list[dict], bm25: BM25Okapi,
                k: int = 3) -> list[dict]:
    scores = bm25.get_scores(tokenize(question))
    top = np.argsort(scores)[::-1][:k]
    return [{**chunks[i], "score": float(scores[i])} for i in top]


# ======================================================================
# 2. HYBRID - RECIPROCAL RANK FUSION (RRF)
#
# Problem: dense scores are cosines (0..1) and BM25 scores are unbounded
# (0..30+). You cannot add them - the scales are meaningless together.
#
# RRF solves it by throwing the scores away and using only the RANKS:
#
#     score(chunk) = sum over each list of  1 / (k + rank_in_that_list)
#
# k (=60 by convention) softens the difference between rank 1 and rank 2,
# so a chunk ranked 2nd by BOTH methods can beat a chunk ranked 1st by one
# method and 50th by the other. Agreement across methods is what wins.
# ======================================================================
def reciprocal_rank_fusion(ranked_lists: list[list[dict]], k: int = 60,
                           top_k: int = 3) -> list[dict]:
    fused: dict[str, dict] = {}
    for ranked in ranked_lists:
        for rank, chunk in enumerate(ranked, start=1):
            cid = chunk["chunk_id"]
            if cid not in fused:
                fused[cid] = {**chunk, "score": 0.0}
            fused[cid]["score"] += 1.0 / (k + rank)
    out = sorted(fused.values(), key=lambda c: c["score"], reverse=True)
    return out[:top_k]


def hybrid_search(question: str, chunks: list[dict], matrix, bm25: BM25Okapi,
                  dense_search_fn, k: int = 3, pool: int = 10) -> list[dict]:
    """
    Take the top `pool` from EACH method, then fuse.

    pool > k on purpose: a chunk ranked 7th by dense and 2nd by BM25 should
    get a chance. If we only fused the top 3 of each we would never see it.
    """
    dense_hits = dense_search_fn(question, chunks, matrix, k=pool)
    sparse_hits = bm25_search(question, chunks, bm25, k=pool)
    return reciprocal_rank_fusion([dense_hits, sparse_hits], top_k=k)


# ======================================================================
# 3. RERANKING - CROSS-ENCODER
#
# Bi-encoder (Week 3): encodes question and chunk SEPARATELY into vectors,
#   then compares. Fast, because chunk vectors are precomputed. But the two
#   texts never meet, so it cannot reason about how they relate.
#
# Cross-encoder: feeds "question [SEP] chunk" through the model TOGETHER and
#   outputs one relevance score. Far more accurate. Far slower - nothing can
#   be precomputed, so it only runs on a shortlist.
#
# Standard pattern: retrieve 20 cheaply, rerank those 20 properly, keep 3.
# ======================================================================
_reranker = None


def get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        _reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _reranker


def rerank(question: str, candidates: list[dict], k: int = 3) -> list[dict]:
    if not candidates:
        return []
    model = get_reranker()
    pairs = [(question, f"{c['section']}\n{c['text']}") for c in candidates]
    scores = model.predict(pairs)
    order = np.argsort(scores)[::-1][:k]
    return [{**candidates[i], "score": float(scores[i])} for i in order]
