"""
WEEK 4 - Did the retrieval change actually fix the ANSWERS?

measure.py scores retrieval only (free). But the deliverable is an app that
answers questions, so we must close the loop: re-ask the Week 3 questions
that failed, using the improved retrieval, and compare the answers.

Costs ~3 API calls.
Run:  python week4/recheck.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from week3 import rag
from week4 import retrieval
from llm import ask, print_stats

# The Week 3 question that failed, plus two that passed (to check we did not
# break anything - a change that fixes one thing and breaks two is a loss).
QUESTIONS = [
    ("Which decline codes cascade to the next acquirer, and which do not?",
     "FAILED in week 3 - said I don't know"),
    ("What is the difference between ERR-4032 and ERR-4033?",
     "passed in week 3 - must still pass"),
    ("Can I refund a payment that is 200 days old?",
     "passed in week 3 - must still pass"),
]

print("Building indexes...")
chunks = rag.build_chunks(chunk_size=600, overlap=100)
matrix = rag.embed_chunks(chunks)
bm25 = retrieval.build_bm25(chunks)
print(f"{len(chunks)} chunks.\n")


def answer_with(question, retrieve_fn):
    hits = retrieve_fn(question)
    prompt = rag.build_prompt(question, hits)
    text = ask(prompt, temperature=0.0, seed=42, system=rag.SYSTEM)
    return hits, text


def dense_only(q):
    return rag.search(q, chunks, matrix, k=3)


def improved(q):
    # hybrid retrieve 12, then cross-encoder rerank down to 3
    wide = retrieval.hybrid_search(q, chunks, matrix, bm25, rag.search, k=12)
    return retrieval.rerank(q, wide, k=3)


for question, note in QUESTIONS:
    print("=" * 78)
    print(f"Q: {question}")
    print(f"   ({note})")
    print("=" * 78)

    hits, text = answer_with(question, improved)
    print("  chunks now retrieved:")
    for h in hits:
        preview = " ".join(h["text"].split())[:62]
        print(f"    {h['doc_id']:<26} > {h['section']:<28} {preview}...")
    print(f"\n  ANSWER: {text}\n")

print_stats()
