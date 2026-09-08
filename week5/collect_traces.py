"""
WEEK 5 - STEP 1: collect real traces from the app.

A TRACE is a complete record of one request:
    the question, what was retrieved (with scores), and what was answered -
    detailed enough to replay the whole thing later without re-running it.

We run the app in its BASELINE configuration (dense retrieval, top 3) because
that is the app whose failures we want to study. Studying an already-fixed app
teaches you nothing.

Saves two files:
    week5/traces.json  - machine readable, for scoring
    week5/traces.md    - human readable, for YOU to read and annotate

~21 API calls. Cached, so re-running is free.
Run:  python week5/collect_traces.py
"""
import sys, os, json, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from week3 import rag
from week4.evalset import EVAL_SET, OUT_OF_SCOPE, contains
from llm import ask, MODEL, print_stats

REFUSAL = "i don't know"

print("Building index (baseline: dense only, chunk 600, k=3)...")
chunks = rag.build_chunks(chunk_size=600, overlap=100)
matrix = rag.embed_chunks(chunks)
print(f"{len(chunks)} chunks\n")

traces = []

# ---- questions that SHOULD be answerable -----------------------------
for i, item in enumerate(EVAL_SET, 1):
    t = rag.answer(item["q"], chunks, matrix, k=3)

    # Objective facts about this trace - no judgement yet. Judgement comes
    # from reading, in step 2. These are just things a rule can check.
    answer_text = t["answer"]
    retrieved_text = " ".join(c["text"] for c in t["retrieved"])

    traces.append({
        "id": f"T{i:02d}",
        "question": item["q"],
        "kind": item["kind"],
        "expected_source": item["gold"],
        "needed_text": item["must"],
        "answerable": True,
        "retrieved": [
            {"doc": c["doc_id"], "section": c["section"],
             "score": round(c["score"], 4),
             "text": c["text"]}
            for c in t["retrieved"]
        ],
        "answer": answer_text,
        "cited_sources": t["sources"],
        "facts": {
            "answer_text_was_retrieved": contains(retrieved_text, item["must"]),
            "right_doc_retrieved": any(c["doc_id"] in item["gold"] for c in t["retrieved"]),
            "app_refused": REFUSAL in answer_text.lower(),
            "has_citation": bool(t["sources"]),
        },
    })
    print(f"  {i:>2}/{len(EVAL_SET) + len(OUT_OF_SCOPE)}  {item['q'][:58]}")

# ---- questions that should be REFUSED --------------------------------
for j, q in enumerate(OUT_OF_SCOPE, 1):
    t = rag.answer(q, chunks, matrix, k=3)
    answer_text = t["answer"]
    traces.append({
        "id": f"T{len(EVAL_SET) + j:02d}",
        "question": q,
        "kind": "out_of_scope",
        "expected_source": [],
        "needed_text": None,
        "answerable": False,
        "retrieved": [
            {"doc": c["doc_id"], "section": c["section"],
             "score": round(c["score"], 4), "text": c["text"]}
            for c in t["retrieved"]
        ],
        "answer": answer_text,
        "cited_sources": t["sources"],
        "facts": {
            "answer_text_was_retrieved": None,
            "right_doc_retrieved": None,
            "app_refused": REFUSAL in answer_text.lower(),
            "has_citation": bool(t["sources"]),
        },
    })
    print(f"  {len(EVAL_SET) + j:>2}/{len(EVAL_SET) + len(OUT_OF_SCOPE)}  {q[:58]}")

# ---- save ------------------------------------------------------------
here = os.path.dirname(os.path.abspath(__file__))
meta = {
    "collected_at": datetime.datetime.now().isoformat(timespec="seconds"),
    "model": MODEL,
    "config": "dense only, chunk_size=600, overlap=100, k=3",
    "count": len(traces),
}
with open(os.path.join(here, "traces.json"), "w", encoding="utf-8") as f:
    json.dump({"meta": meta, "traces": traces}, f, indent=1)

with open(os.path.join(here, "traces.md"), "w", encoding="utf-8") as f:
    f.write(f"# Week 5 traces\n\n{meta['count']} traces · {meta['model']}\n")
    f.write(f"Config: {meta['config']}\n\n")
    for t in traces:
        f.write(f"\n---\n\n## {t['id']}  [{t['kind']}]\n\n")
        f.write(f"**Q:** {t['question']}\n\n")
        f.write(f"**A:** {t['answer']}\n\n")
        f.write(f"- expected source: `{t['expected_source']}`\n")
        f.write(f"- needed text: `{t['needed_text']}`\n")
        f.write(f"- cited: `{t['cited_sources']}`\n")
        f.write(f"- facts: `{t['facts']}`\n\n")
        f.write("**Retrieved:**\n\n")
        for c in t["retrieved"]:
            preview = " ".join(c["text"].split())[:150]
            f.write(f"- `{c['score']}` {c['doc']} > {c['section']} — {preview}...\n")
        f.write("\n**My note:** _(to fill in)_\n")

# ---- quick objective summary ----------------------------------------
ans = [t for t in traces if t["answerable"]]
oos = [t for t in traces if not t["answerable"]]
print("\n" + "=" * 70)
print("OBJECTIVE FACTS (no judgement yet - that comes from reading)")
print("=" * 70)
print(f"  traces collected            : {len(traces)}")
print(f"  answerable questions        : {len(ans)}")
print(f"    answer text was retrieved : {sum(t['facts']['answer_text_was_retrieved'] for t in ans)}")
print(f"    right document retrieved  : {sum(t['facts']['right_doc_retrieved'] for t in ans)}")
print(f"    app refused anyway        : {sum(t['facts']['app_refused'] for t in ans)}   <- false refusals")
print(f"    answer carried a citation : {sum(t['facts']['has_citation'] for t in ans)}")
print(f"  out-of-scope questions      : {len(oos)}")
print(f"    correctly refused         : {sum(t['facts']['app_refused'] for t in oos)}")
print("\n  saved: week5/traces.json  and  week5/traces.md")
print_stats()
