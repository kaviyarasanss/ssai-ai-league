"""
WEEK 1 - EXPERIMENT 5: Embeddings. Zero API calls - runs on your CPU.

An embedding turns a piece of text into a list of numbers (a "vector") that
represents its MEANING. Two texts that mean the same thing get vectors that
point in nearly the same direction, even with no words in common.

This is the engine of Week 3. RAG works by embedding your documents once,
embedding the user's question, and finding which document vector points
most nearly the same way.

First run downloads ~80MB. After that it is offline and instant.

Run:  python week1/05_embeddings.py
"""
import numpy as np
from sentence_transformers import SentenceTransformer

# A "bi-encoder": encodes each text independently into one vector.
# Small, fast, CPU-friendly, and from the same family your Week 3 brief
# names (MTEB / BGE / E5).
print("Loading model (first run downloads ~80MB)...")
model = SentenceTransformer("all-MiniLM-L6-v2")
print("ready.\n")


def embed(text: str) -> np.ndarray:
    return model.encode(text)


def similarity(a: str, b: str) -> float:
    """
    Cosine similarity: how closely two vectors point the same way.
     1.0 = identical direction, 0.0 = unrelated, negative = opposite.
    """
    va, vb = embed(a), embed(b)
    return float(np.dot(va, vb) / (np.linalg.norm(va) * np.linalg.norm(vb)))


# ----------------------------------------------------------------------
print("=" * 72)
print("1. TEXT BECOMES NUMBERS")
print("=" * 72)
v = embed("The payment failed.")
print(f"  'The payment failed.'  ->  vector of {len(v)} numbers")
print(f"  first 8: {np.round(v[:8], 4)}")
print("  Every text you embed becomes exactly this many numbers.\n")

# ----------------------------------------------------------------------
print("=" * 72)
print("2. MEANING BEATS KEYWORDS  <- the whole point of RAG")
print("=" * 72)
question = "How do I get my money back?"
candidates = [
    "Refunds are issued to the original card within 5 business days.",
    "Please put the money back in the petty cash box.",
    "Our office is located on Back Street.",
]
print(f"  question: {question!r}\n")
for c in candidates:
    shared = set(question.lower().replace("?", "").split()) & set(c.lower().split())
    print(f"  sim={similarity(question, c):.3f}   words in common: {len(shared)}")
    print(f"     {c}")
print("\n  The best match shares almost NO words with the question.")
print("  Keyword search would have ranked it last. That is why we embed.\n")

# ----------------------------------------------------------------------
print("=" * 72)
print("3. WHERE EMBEDDINGS FAIL  <- this is why Week 4 adds keyword search")
print("=" * 72)
pairs = [
    ("ERR-4032", "ERR-4033"),
    ("ERR-4032", "ERR-9999"),
    ("invoice INV-2024-881", "invoice INV-2024-882"),
]
for a, b in pairs:
    print(f"  sim={similarity(a, b):.3f}   {a!r}  vs  {b!r}")
print("\n  Near-identical scores for DIFFERENT codes. Embeddings capture")
print("  'looks like an error code', not WHICH code. Ask about ERR-4032 and")
print("  you may get the ERR-4033 document. Week 4 fixes this with BM25.\n")

# ----------------------------------------------------------------------
print("=" * 72)
print("4. STATIC vs CONTEXTUAL EMBEDDINGS")
print("=" * 72)
s1 = "The bank declined the charge on my card."
s2 = "We charge the battery overnight before the trip."
s3 = "The issuer rejected the transaction on my credit card."
print(f"  A: {s1}")
print(f"  B: {s2}")
print(f"  C: {s3}\n")
print(f"  A vs B  sim={similarity(s1, s2):.3f}   both contain 'charge'")
print(f"  A vs C  sim={similarity(s3, s1):.3f}   no shared keyword at all")
print("\n  Word2Vec / GloVe are STATIC: one fixed vector for 'charge', so A and B")
print("  would look similar. This model is CONTEXTUAL - it reads the whole")
print("  sentence, so 'charge' means something different in each and A lands")
print("  next to C instead. Contextual is why modern RAG works.")
