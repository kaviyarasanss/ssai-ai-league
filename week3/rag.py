"""
WEEK 3 - The RAG engine.  Track E: developer documentation.

The whole pipeline, in order:

    documents  ->  chunks  ->  embeddings  ->  (stored)
                                                  |
    question   ->  embedding  ->  cosine search --+--> top-K chunks
                                                          |
                                          prompt with ONLY those chunks
                                                          |
                                                    grounded answer + citations

Nothing here is magic. Steps 1-4 are ordinary Python and cost zero API calls.
Only the final answer costs a call.
"""
import os
import re
import sys
import pathlib

import numpy as np
from sentence_transformers import SentenceTransformer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from llm import ask  # noqa: E402

DOCS_DIR = pathlib.Path(__file__).parent / "docs"

# The embedding model. A BI-ENCODER: it turns each text into one vector
# independently. Runs locally on CPU - no API, no quota, no cost.
_encoder = None


def get_encoder() -> SentenceTransformer:
    """Load the model once and reuse it (loading takes a few seconds)."""
    global _encoder
    if _encoder is None:
        _encoder = SentenceTransformer("all-MiniLM-L6-v2")
    return _encoder


# ======================================================================
# STEP 1 - LOAD
# ======================================================================
def load_documents(folder: pathlib.Path = DOCS_DIR) -> list[dict]:
    """Read every .md file in the folder into a dict."""
    docs = []
    for path in sorted(folder.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        first_line = text.strip().splitlines()[0]
        docs.append({
            "doc_id": path.name,
            "title": first_line.lstrip("# ").strip(),
            "text": text,
        })
    return docs


# ======================================================================
# STEP 2 - CHUNK
#
# Why chunk at all? Two reasons:
#   1. The context window is finite - we cannot paste 10 documents in.
#   2. Precision. If we embed a whole document into ONE vector, that vector
#      is an average of everything in it, and matches nothing well.
#
# Strategy: split on markdown "## " headings first, because a heading marks a
# real topic boundary. Only if a section is still too big do we cut it by
# character count, with overlap.
#
# OVERLAP matters: a hard cut can slice a sentence - or worse, separate
# "ERR-4032" from the sentence explaining it. Overlap repeats the last N
# characters at the start of the next chunk so a fact spanning a boundary
# survives in at least one chunk intact.
# ======================================================================
# Chunks shorter than this are dropped. A 9-character fragment like "## Timing"
# is a heading with no content - it can win a search and then tell the model
# nothing, which produces a confident empty answer.
MIN_CHUNK_CHARS = 60


def chunk_document(doc: dict, chunk_size: int = 600, overlap: int = 100) -> list[dict]:
    chunks = []
    # Split on '## ' headings, keeping the heading with its content.
    sections = re.split(r"\n(?=## )", doc["text"])

    for section in sections:
        section = section.strip()
        if not section:
            continue

        heading_match = re.match(r"#{1,3}\s+(.+)", section)
        heading = heading_match.group(1).strip() if heading_match else doc["title"]

        if len(section) <= chunk_size:
            pieces = [section]
        else:
            # Section too long: slide a window over it with overlap.
            pieces = []
            start = 0
            while start < len(section):
                pieces.append(section[start:start + chunk_size])
                start += chunk_size - overlap   # step back by `overlap`

        for piece in pieces:
            if len(piece.strip()) < MIN_CHUNK_CHARS:
                continue
            chunks.append({
                "chunk_id": f"{doc['doc_id']}#{len(chunks)}",
                "doc_id": doc["doc_id"],
                "title": doc["title"],
                "section": heading,
                "text": piece.strip(),
            })
    return chunks


def build_chunks(chunk_size: int = 600, overlap: int = 100,
                 folder: pathlib.Path = DOCS_DIR) -> list[dict]:
    """Load every document and chunk them all."""
    chunks = []
    for doc in load_documents(folder):
        chunks.extend(chunk_document(doc, chunk_size, overlap))
    return chunks


# ======================================================================
# STEP 3 - EMBED  (this is the "vector store", kept in memory)
# ======================================================================
def embed_chunks(chunks: list[dict]) -> np.ndarray:
    """
    Turn every chunk into a vector. Returns a matrix of shape
    (number_of_chunks, 384).

    normalize_embeddings=True makes every vector length 1, which means
    cosine similarity becomes a plain dot product - faster, and the reason
    the search function below is one line of maths.
    """
    texts = [f"{c['title']} - {c['section']}\n{c['text']}" for c in chunks]
    return get_encoder().encode(texts, normalize_embeddings=True,
                                show_progress_bar=False)


# ======================================================================
# STEP 4 - SEARCH
# ======================================================================
def search(question: str, chunks: list[dict], matrix: np.ndarray,
           k: int = 3) -> list[dict]:
    """
    Find the k chunks whose vectors point most nearly the same way as the
    question's vector.

    Because all vectors are normalised, matrix @ q IS the cosine similarity
    of every chunk against the question, computed in one operation.
    """
    q = get_encoder().encode(question, normalize_embeddings=True)
    scores = matrix @ q                      # one score per chunk
    top = np.argsort(scores)[::-1][:k]       # indices of the k highest

    return [{**chunks[i], "score": float(scores[i])} for i in top]


# ======================================================================
# STEP 5 - GROUNDED GENERATION
# ======================================================================
SYSTEM = """You answer questions about the PhoenixPay SDK using ONLY the \
numbered context passages provided.

Rules:
- Use only facts stated in the context. Never use outside knowledge.
- Cite the passage number in square brackets after each fact, like [2].
- If the context does not contain the answer, reply with exactly:
  I don't know - that is not covered in the documentation.
- Do not guess, and do not describe features that are not in the context."""

# If the best chunk scores below this, we refuse WITHOUT calling the model.
# Free: saves a request, and stops a weak match becoming a confident answer.
MIN_SCORE = 0.25


def build_prompt(question: str, hits: list[dict]) -> str:
    """Assemble the numbered context block plus the question."""
    blocks = []
    for i, h in enumerate(hits, 1):
        blocks.append(f"[{i}] (source: {h['doc_id']} > {h['section']})\n{h['text']}")
    context = "\n\n".join(blocks)
    return f"CONTEXT:\n{context}\n\nQUESTION: {question}\n\nANSWER:"


def answer(question: str, chunks: list[dict], matrix: np.ndarray,
           k: int = 3, use_cache: bool = True) -> dict:
    """
    Full pipeline for one question. Returns a TRACE - not just the answer.

    A trace records the question, what was retrieved (with scores), and what
    was generated. Week 5 requires exactly this: enough detail to replay any
    answer later and work out which half went wrong.
    """
    hits = search(question, chunks, matrix, k=k)
    top_score = hits[0]["score"] if hits else 0.0

    if top_score < MIN_SCORE:
        return {
            "question": question,
            "retrieved": hits,
            "top_score": top_score,
            "answer": "I don't know - that is not covered in the documentation.",
            "refused_before_llm": True,
            "sources": [],
        }

    prompt = build_prompt(question, hits)
    text = ask(prompt, temperature=0.0, seed=42, system=SYSTEM, use_cache=use_cache)

    # Which passages did it actually cite?
    cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", text)
                    if 1 <= int(n) <= len(hits)})

    return {
        "question": question,
        "retrieved": hits,
        "top_score": top_score,
        "answer": text,
        "refused_before_llm": False,
        "sources": [f"{hits[i - 1]['doc_id']} > {hits[i - 1]['section']}" for i in cited],
    }
