"""
WEEK 4 - Measuring retrieval. ZERO API CALLS.

The key insight of this week: you can measure whether the RIGHT DOCUMENT was
fetched without ever calling the LLM. Retrieval quality is pure maths.

Metrics (k = 3 throughout):

  hit-rate@k  Did at least one gold document appear in the top k?
              Averaged over all questions. "How often do we even have a
              chance of answering correctly?"

  recall@k    Of all the gold documents for a question, what fraction
              appeared in the top k? Matters when several documents are
              needed to answer fully.

  MRR         Mean Reciprocal Rank. 1/(rank of the first gold document),
              averaged. Rank 1 -> 1.0, rank 2 -> 0.5, rank 3 -> 0.33,
              not found -> 0. Rewards putting the right doc at the TOP,
              not merely somewhere in the list.

Run:
    python week4/measure.py              dense vs bm25 vs hybrid
    python week4/measure.py --rerank     also test the cross-encoder
                                          (downloads ~80MB the first time)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from week3 import rag
from week4 import retrieval
from week4.evalset import EVAL_SET, contains


# ======================================================================
# METRICS
# ======================================================================
def evaluate(retrieve_fn, k: int = 3) -> dict:
    """Run every eval question through one retrieval strategy and score it."""
    hits, recalls, rr, per_question, available = 0, [], [], [], 0

    for item in EVAL_SET:
        chunks = retrieve_fn(item["q"], k)
        found_docs = [h["doc_id"] for h in chunks]
        gold = set(item["gold"])

        # ANSWER AVAILABLE: does any RETRIEVED CHUNK actually contain the
        # text needed to answer? This is stricter than hit-rate, which only
        # asks whether the right FILE was fetched. The cascade question
        # passes hit-rate (right file) but fails this (the chunk holding the
        # table never made the top 3) - which is exactly the real failure.
        got_answer = any(contains(c["text"], item["must"]) for c in chunks)
        available += 1 if got_answer else 0

        # hit-rate: was ANY gold doc retrieved?
        hit = any(d in gold for d in found_docs)
        hits += 1 if hit else 0

        # recall: what FRACTION of gold docs were retrieved?
        recalls.append(len(gold & set(found_docs)) / len(gold))

        # MRR: 1 / position of the first gold doc
        rank = next((i for i, d in enumerate(found_docs, 1) if d in gold), None)
        rr.append(1.0 / rank if rank else 0.0)

        per_question.append({
            "q": item["q"], "kind": item["kind"], "gold": item["gold"],
            "found": found_docs, "hit": hit, "rank": rank,
            "answer_available": got_answer, "must": item["must"],
        })

    n = len(EVAL_SET)
    return {
        "answer_available": available / n,
        "hit_rate": hits / n,
        "recall": sum(recalls) / n,
        "mrr": sum(rr) / n,
        "per_question": per_question,
    }


def by_kind(result: dict) -> dict:
    """Break the hit-rate down by question type - where did the change help?"""
    groups = {}
    for row in result["per_question"]:
        groups.setdefault(row["kind"], []).append(row["hit"])
    return {k: sum(v) / len(v) for k, v in sorted(groups.items())}


# ======================================================================
# STRATEGIES
# ======================================================================
def build(chunk_size: int, overlap: int):
    chunks = rag.build_chunks(chunk_size=chunk_size, overlap=overlap)
    matrix = rag.embed_chunks(chunks)
    bm25 = retrieval.build_bm25(chunks)
    return chunks, matrix, bm25


def main() -> None:
    want_rerank = "--rerank" in sys.argv

    print("Building indexes (local, no API calls)...")
    c600, m600, b600 = build(600, 100)
    c1200, m1200, b1200 = build(1200, 200)
    print(f"  chunk_size=600  -> {len(c600)} chunks")
    print(f"  chunk_size=1200 -> {len(c1200)} chunks\n")

    strategies = {
        "A  BASELINE dense only, chunk 600":
            lambda q, k: rag.search(q, c600, m600, k=k),
        "B  bm25 keyword only, chunk 600":
            lambda q, k: retrieval.bm25_search(q, c600, b600, k=k),
        "C  HYBRID dense+bm25 RRF, chunk 600":
            lambda q, k: retrieval.hybrid_search(q, c600, m600, b600, rag.search, k=k),
        "D  dense only, chunk 1200":
            lambda q, k: rag.search(q, c1200, m1200, k=k),
    }
    if want_rerank:
        # ONE change from baseline A: keep dense retrieval, but pull 12
        # candidates instead of 3 and let a cross-encoder pick the best 3.
        strategies["E  dense + cross-encoder rerank"] = (
            lambda q, k: retrieval.rerank(q, rag.search(q, c600, m600, k=12), k=k)
        )
        # Two changes stacked - reported separately so it is never confused
        # with a single-change result.
        strategies["F  hybrid + rerank (2 changes)"] = (
            lambda q, k: retrieval.rerank(
                q, retrieval.hybrid_search(q, c600, m600, b600, rag.search, k=12), k=k)
        )

    results = {name: evaluate(fn, k=3) for name, fn in strategies.items()}

    print("=" * 84)
    print(f"{'strategy':<38} {'ANSWER@3':>9} {'hit@3':>7} {'recall@3':>9} {'MRR':>7}")
    print("=" * 84)
    for name, r in results.items():
        print(f"{name:<38} {r['answer_available']:>9.3f} {r['hit_rate']:>7.3f} "
              f"{r['recall']:>9.3f} {r['mrr']:>7.3f}")
    print()
    print("  ANSWER@3 = did a retrieved chunk actually CONTAIN the answer text?")
    print("  hit@3    = was the right FILE fetched? (blind to wrong-chunk failures)")

    print()
    print("=" * 84)
    print("HIT-RATE@3 BY QUESTION TYPE  (this is where the story is)")
    print("=" * 84)
    kinds = sorted({e["kind"] for e in EVAL_SET})
    print(f"{'strategy':<38} " + " ".join(f"{k:>12}" for k in kinds))
    for name, r in results.items():
        bk = by_kind(r)
        print(f"{name:<38} " + " ".join(f"{bk.get(k, 0):>12.3f}" for k in kinds))

    # --- each candidate ONE change, as a before/after -----------------
    base = results["A  BASELINE dense only, chunk 600"]

    print()
    print("=" * 84)
    print("CANDIDATE SINGLE CHANGES vs BASELINE A")
    print("=" * 84)
    for label, key in [
        ("add BM25 + RRF fusion", "C  HYBRID dense+bm25 RRF, chunk 600"),
        ("raise chunk size to 1200", "D  dense only, chunk 1200"),
        ("add cross-encoder rerank", "E  dense + cross-encoder rerank"),
    ]:
        if key not in results:
            continue
        r = results[key]
        print(f"  {label:<28} answer@3 {base['answer_available']:.3f} -> "
              f"{r['answer_available']:.3f} ({r['answer_available'] - base['answer_available']:+.3f})   "
              f"MRR {base['mrr']:.3f} -> {r['mrr']:.3f}")

    # pick the winner on answer-availability, tie-break on MRR
    candidates = [k for k in ("C  HYBRID dense+bm25 RRF, chunk 600",
                              "D  dense only, chunk 1200",
                              "E  dense + cross-encoder rerank") if k in results]
    best = max(candidates,
               key=lambda k: (results[k]["answer_available"], results[k]["mrr"]))
    change = results[best]
    delta = change["hit_rate"] - base["hit_rate"]

    print()
    print("=" * 84)
    print(f"BEST SINGLE CHANGE: {best}")
    print("=" * 84)
    print(f"  answer-available@3  {base['answer_available']:.3f} -> "
          f"{change['answer_available']:.3f}  "
          f"({change['answer_available'] - base['answer_available']:+.3f})")
    print(f"  hit-rate@3          {base['hit_rate']:.3f} -> {change['hit_rate']:.3f}  ({delta:+.3f})")
    print(f"  MRR  {base['mrr']:.3f} -> {change['mrr']:.3f}  ({change['mrr'] - base['mrr']:+.3f})")

    # --- what it did NOT fix ------------------------------------------
    print()
    print("=" * 84)
    print("ANSWER STILL NOT RETRIEVED AFTER THE CHANGE")
    print("=" * 84)
    still, fixed = [], []
    for b, a in zip(base["per_question"], change["per_question"]):
        if not a["answer_available"]:
            still.append(a)
        elif not b["answer_available"]:
            fixed.append(a)

    if fixed:
        print(f"\n  FIXED by the change ({len(fixed)}):")
        for row in fixed:
            print(f"    [{row['kind']}] {row['q']}")
    if still:
        print(f"\n  STILL BROKEN ({len(still)}):")
        for row in still:
            print(f"    [{row['kind']}] {row['q']}")
            print(f"        needed text : {row['must']!r}")
            print(f"        got chunks from: {row['found']}")
    else:
        print("\n  None - every question retrieves a gold document in the top 3.")


if __name__ == "__main__":
    main()
