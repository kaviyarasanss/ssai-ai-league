# Week 3 — Retrieval & RAG: terms and evaluator answers

## Every term in the brief

**Why RAG** — the model's weights contain no copy of your documents. You cannot
make it *remember* them. You can only put the right text in front of it at
question time. RAG = retrieve first, then generate from what you retrieved.

**Dense retrieval** — search by comparing *vectors* (meaning). Opposite of
sparse/keyword retrieval (BM25), which compares *words*. "Dense" because the
vector is 384 numbers that are nearly all non-zero; a keyword vector is mostly
zeros ("sparse").

**Bi-encoder** — encodes the question and each document *separately* into one
vector each, then compares. Fast: document vectors are computed once, in
advance. Weakness: it never sees the question and document together, so it
cannot reason about how they relate. This is what `all-MiniLM-L6-v2` is.

**Cross-encoder** — feeds question AND document into the model *together* and
outputs one relevance score. Much more accurate, far slower — you cannot
pre-compute it, so it must run at query time on a shortlist. Used for
reranking (Week 4).

**Embedding models / MTEB / BGE / E5** — MTEB is the public leaderboard that
benchmarks embedding models. BGE and E5 are two well-known open families.
`all-MiniLM-L6-v2` is small (384 dims), fast, CPU-friendly, good enough here.
Bigger models (1024 dims) score better and cost more time and memory.

**Chunking strategies** — fixed-size, sentence-based, paragraph-based, or
structure-aware (split on headings). We use structure-aware first, falling
back to fixed-size with overlap for long sections.

**Chunk size & overlap** —
- Small chunks: precise match, but the answer may be cut in half.
- Big chunks: complete context, but the score gets diluted by unrelated text
  in the same chunk, and you pay more tokens.
- Overlap repeats the last N characters at the start of the next chunk so a
  fact sitting on a boundary survives intact somewhere.

**Vector database** — stores vectors and finds nearest neighbours fast.
- **Qdrant** — standalone vector DB, production-grade, runs in Docker.
- **Chroma** — lightweight, embedded, good for prototypes.
- **pgvector** — a Postgres extension; keeps vectors next to your relational
  data so you can filter with plain SQL.
We use a numpy matrix in memory. At 47 chunks a brute-force scan is instant;
a vector DB earns its keep at ~100k+ vectors.

**HNSW** — Hierarchical Navigable Small World. The index algorithm vector DBs
use. Instead of comparing against every vector (exact, slow), it walks a
layered graph of neighbours and lands on the near-best in log time. It is
**approximate** — it can miss the true top result, and you trade recall for
speed with its `ef_search` parameter.

**Similarity search & top-K** — score every chunk against the question and keep
the K best. K too small = you miss the answer. K too large = you stuff the
prompt with noise, pay more tokens, and give the model more to get confused by.
K=3 to 5 is typical.

**Metadata filtering** — narrow the candidate set by attributes *before* or
*during* the vector search: `doc_type = "error_codes"`, `version >= 2.0`,
`language = "en"`. Cheap and very effective. A vector search that can only
ever look at the right 5% of the corpus is both faster and more accurate.

**Grounded generation & citations** — the model is instructed to answer ONLY
from the supplied passages and to cite which passage each fact came from.
"Grounded" = every claim traceable to retrieved text. Citations are what make
the answer checkable by a human.

## Likely evaluator questions

**Q: Why not just paste all 10 documents into the prompt?**
Ours would fit, but it doesn't scale, you pay for every token on every call,
and accuracy drops for facts buried mid-context ("lost in the middle").
Retrieval keeps the prompt small and relevant.

**Q: Why chunk instead of embedding whole documents?**
One vector per document is an *average* of everything in it, so it matches
everything weakly and nothing strongly. Chunks keep the vector focused on one
topic.

**Q: How does it know it doesn't know?**
Two independent guards. (1) If the best similarity score is below MIN_SCORE
(0.25) we return "I don't know" *without* calling the model at all — free, and
it stops a weak match becoming a confident answer. (2) The system prompt
instructs the model to reply "I don't know" if the context lacks the answer.

**Q: Why is the similarity just `matrix @ q`?**
We embed with `normalize_embeddings=True`, so every vector has length 1.
Cosine = dot / (|a|·|b|), and both lengths are 1, so cosine == dot product.
One matrix multiply scores every chunk at once.

**Q: What is the weakest part of this system?**
Exact identifiers. Embeddings score `ERR-4032` vs `ERR-4033` at 0.970 — they
encode "looks like an error code", not which one. For a developer-docs corpus
full of codes, that is the top failure risk. Week 4 fixes it with BM25 keyword
search fused into a hybrid, plus a cross-encoder reranker.

**Q: Where would prompt injection hit this?**
Indirect injection: a malicious instruction sitting inside a *document* that
gets retrieved and pasted into the prompt as trusted context. Mitigation is to
label retrieved text as data, never let it trigger actions, and keep tools
least-privilege.
