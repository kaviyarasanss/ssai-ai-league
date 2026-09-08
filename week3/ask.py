"""
WEEK 3 - "Ask my documents". The Week 3 deliverable.

  python week3/ask.py                    run the demo question set
  python week3/ask.py "your question"    ask one question
  python week3/ask.py --chunks           compare chunk sizes (no API calls)

Mentor checks this answers:
  - correct answer from the documents        -> demo set, questions 1-5
  - every answer shows its source            -> 'sources:' line
  - admits when it does not know             -> questions 6-7
  - tried more than one chunk size           -> --chunks
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from week3 import rag
from llm import print_stats, MODEL

# Questions 1-5 ARE answerable from the docs. 6-7 are NOT - the app must refuse.
DEMO_QUESTIONS = [
    "What is the difference between ERR-4032 and ERR-4033?",
    "Which decline codes cascade to the next acquirer, and which do not?",
    "How long are idempotency keys stored, and what should I derive one from?",
    "What happens if my webhook endpoint does not respond in time?",
    "Can I refund a payment that is 200 days old?",
    "What is the SDK's monthly pricing for the Enterprise plan?",   # not in docs
    "How do I integrate PhoenixPay with Salesforce?",                # not in docs
]


def show(trace: dict) -> None:
    print("=" * 78)
    print(f"Q: {trace['question']}")
    print("-" * 78)
    print(f"A: {trace['answer']}")
    print()
    if trace["refused_before_llm"]:
        print(f"   [refused before calling the model - top score "
              f"{trace['top_score']:.3f} < {rag.MIN_SCORE}]")
    else:
        print(f"   sources: {', '.join(trace['sources']) or '(none cited)'}")
    print(f"   retrieved (top {len(trace['retrieved'])}):")
    for h in trace["retrieved"]:
        print(f"     {h['score']:.3f}  {h['doc_id']:<26} > {h['section']}")
    print()


def compare_chunk_sizes() -> None:
    """Chunking is free - no API calls. Show what the setting actually does."""
    probe = "Which decline codes cascade to the next acquirer?"
    print(f"Probe question: {probe!r}\n")
    for size, overlap in [(300, 60), (600, 100), (1200, 200)]:
        chunks = rag.build_chunks(chunk_size=size, overlap=overlap)
        matrix = rag.embed_chunks(chunks)
        hits = rag.search(probe, chunks, matrix, k=3)
        print(f"chunk_size={size:<5} overlap={overlap:<4} -> {len(chunks)} chunks")
        for h in hits:
            preview = " ".join(h["text"].split())[:70]
            print(f"    {h['score']:.3f}  {h['doc_id']:<26} {preview}...")
        print()
    print("Smaller chunks  = sharper match, but the answer may be cut in half.")
    print("Bigger chunks   = full context, but the score gets diluted by")
    print("                  unrelated text sitting in the same chunk.")


def main() -> None:
    args = sys.argv[1:]

    if args and args[0] == "--chunks":
        compare_chunk_sizes()
        return

    print(f"Loading documents and building the index (model: {MODEL})...")
    chunks = rag.build_chunks(chunk_size=600, overlap=100)
    matrix = rag.embed_chunks(chunks)
    print(f"{len(chunks)} chunks indexed.\n")

    questions = [" ".join(args)] if args else DEMO_QUESTIONS
    for q in questions:
        show(rag.answer(q, chunks, matrix, k=3))

    print_stats()


if __name__ == "__main__":
    main()
