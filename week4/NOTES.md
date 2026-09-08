# Week 4 — Debugging Retrieval: what I did and what I measured

## What the brief asked

> "Take a set of failing questions and sort each one into 'wrong document
> fetched' or 'right document, wrong answer.' Then make one improvement, and
> measure whether the right document now shows up more often — with a
> before-and-after number."
> Track E: "Label the failures, then buy back hit-rate@3 with exactly one change"

## The failure I started from

Week 3 asked 7 questions. One failed:

    Q: Which decline codes cascade to the next acquirer, and which do not?
    A: I don't know - that is not covered in the documentation.

The answer IS in the documents. So which kind of failure is it?

Evidence from the trace — all three retrieved chunks came from the CORRECT
file, `06_routing_cascading.md`. So it was not "wrong document fetched".

Digging into the chunks showed the real cause. The `## Cascading` section is
640 characters. With chunk_size=600 it was split into two chunks:

    chunk A (600 chars) - the heading, a code example, and the full table
    chunk B (140 chars) - the leftover tail, from the overlap. No table.

And chunk B scored HIGHER (0.499) than chunk A (~0.433), so chunk B took the
last of the three slots and chunk A never reached the model.

Why: cosine similarity measures direction. A short chunk has a concentrated
direction. Chunk B is 140 characters almost entirely about cascading, so it
points hard at the query. Chunk A averages a heading, a code block, prose and
a table, so its vector is diluted. **Short and shallow beat long and correct.**

So this is a THIRD category the brief's two buckets do not name:
right document, right section, WRONG CHUNK.

## The measurement problem I found

`hit-rate@3` asks "was the right FILE in the top 3?". For this question the
answer is YES — so the metric scored a PASS on a question the app answered
WRONG.

I was optimising a number that could not see the bug.

So I added a stricter metric, **ANSWER@3**: for each question I recorded the
exact text needed to answer it (e.g. "Cascades?", "ERR-4092", "older than 180
days"), then asked: did any retrieved CHUNK actually contain that text?

| metric | asks | sees wrong-chunk failures? |
|---|---|---|
| hit@3    | right file fetched?  | NO |
| ANSWER@3 | right text fetched?  | YES |

## Results (18 labelled questions, k=3, zero API calls)

| strategy | ANSWER@3 | hit@3 | recall@3 | MRR |
|---|---|---|---|---|
| A BASELINE dense only, chunk 600 | 0.667 | 0.889 | 0.861 | 0.796 |
| B bm25 keyword only              | 0.722 | 0.833 | 0.833 | 0.769 |
| C hybrid dense+bm25 RRF          | 0.778 | 0.889 | 0.889 | 0.833 |
| D dense only, chunk 1200         | 0.722 | 0.889 | 0.861 | 0.796 |
| **E dense + cross-encoder rerank** | **0.833** | 0.889 | 0.889 | 0.861 |
| F hybrid + rerank (TWO changes)  | 0.889 | 0.944 | 0.944 | 0.889 |

**hit@3 is 0.889 for A, C, D and E — completely flat.** Four materially
different systems, one identical score. The old metric could not tell them
apart. ANSWER@3 ranges 0.667 to 0.833 across the same four.

## The one change

Baseline A (dense retrieval only) -> E (dense retrieval, pull 12 candidates,
cross-encoder reranks to 3). Exactly one thing changed.

    ANSWER@3   0.667 -> 0.833   (+0.167)
    MRR        0.796 -> 0.861   (+0.065)
    hit@3      0.889 -> 0.889   (+0.000)

Why reranking and not the others: the failure was a ranking failure, not a
coverage failure. The right chunk was already being retrieved into the
candidate pool — it was just being outranked. A bi-encoder cannot fix that
because it never compares the question and chunk directly. A cross-encoder
reads "which codes cascade" together with each chunk and scores the pair, so
it can see that a 140-character fragment with no table does not answer the
question.

I also measured BM25+RRF (+0.111) and chunk size 1200 (+0.056) separately.
Reranking won. Stacking hybrid AND rerank (strategy F) scores higher still at
0.889, but that is TWO changes and is reported separately so it is never
mistaken for a single-change result.

## Proof it fixed the real answer, not just the metric

`week4/recheck.py` re-asks the failing question through the improved retrieval:

    BEFORE: I don't know - that is not covered in the documentation.

    AFTER:  * Cascades (Soft declines):
              * ERR-4032 insufficient funds [1]
              * ERR-4033 issuer refused [1]
            * Does not cascade (Hard declines):
              * ERR-4034 suspected fraud [1]
              * ERR-4035 card expired [1]

The `## Cascading` chunk moved from missing the top 3 to **rank 1**.
Two questions that already passed in Week 3 still pass — the change fixed one
thing without breaking others.

## What the change FIXED (3)

- Does ERR-4035 cascade to the next acquirer?
- What is ERR-4003?
- Which decline codes cascade, and which do not?   <- the original failure

## What it did NOT fix (3)

| question | needed | why reranking cannot help |
|---|---|---|
| What does ERR-4092 mean? | `ERR-4092` | The chunk was never in the candidate pool. Reranking can only reorder what retrieval already found. Needs BM25 (exact string) or metadata filtering. |
| Why was my payment rejected for being too small? | `Amount below minimum` | Vocabulary gap: user says "too small", doc says "below minimum". Needs query rewriting or HyDE, not reranking. |
| I got a timeout and don't know if the payment went through | `idempotency_key` | Right document retrieved, wrong chunk again. A second instance of the Week 3 bug that reranking did not catch. |

Note the pattern: **reranking fixes ranking problems; it cannot fix retrieval
problems.** If the right chunk never entered the candidate pool, no amount of
re-scoring will surface it.

## Terms used

- **BM25** — keyword/sparse retrieval. Scores by word overlap, weighting rare
  words higher. Knows `ERR-4032` differs from `ERR-4033`; knows nothing about
  meaning. Library: `rank-bm25`, no model download.
- **RRF (Reciprocal Rank Fusion)** — merges two ranked lists using positions,
  not scores, because cosine (0-1) and BM25 (0-30+) are not comparable.
  `score = sum of 1/(60 + rank)`. Agreement across methods wins.
- **Bi-encoder** — encodes question and chunk separately. Fast, precomputable.
  `SentenceTransformer("all-MiniLM-L6-v2")`.
- **Cross-encoder** — encodes question and chunk TOGETHER, outputs one
  relevance score. Accurate, slow, cannot be precomputed, so it only runs on a
  shortlist. `CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")`.
- **hit-rate@k** — was a gold document in the top k?
- **recall@k** — what fraction of gold documents were in the top k?
- **MRR** — 1/(rank of first gold doc), averaged. Rewards ranking it FIRST.
- **MMR** — penalises a candidate for resembling ones already chosen, to avoid
  three near-identical chunks. Not used here; would also have helped.
- **Query rewriting / HyDE** — rewrite the user's wording before searching, or
  generate a fake answer and search with that. The fix for the "too small"
  failure.

## Mentor checklist

- Show, for a specific failure, which kind it is, with evidence — YES, the
  cascade question, with the chunk text and scores as proof.
- One change, not five — YES, three candidates each measured alone; the winner
  (reranking) was one change. The two-change stack is reported separately.
- A before-and-after number — YES, ANSWER@3 0.667 -> 0.833, MRR 0.796 -> 0.861.
- Notice what the change did NOT fix — YES, three named failures with the
  reason each is out of reranking's reach.
