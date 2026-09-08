# Week 4 — what we ran, what came out, what it meant

## The metric problem we found first

`hit-rate@3` asks *"was the right FILE in the top 3?"*. For the week 3 cascade
failure the answer is **yes** — all three chunks came from the right file. The
metric scored a **PASS** on a question the app answered **wrong**.

So we added **`ANSWER@3`**: for each question, record the exact text needed to
answer it, then ask whether any retrieved *chunk* actually contains it.

    {"q": "Which decline codes cascade...?",  "must": "Cascades?"}
    {"q": "What does ERR-4092 mean?",         "must": "ERR-4092"}
    {"q": "Can I refund a 200-day-old payment?", "must": "older than 180 days"}

All 18 labels validated against the corpus. Matching is whitespace-insensitive
because the docs wrap lines mid-phrase ("the issuing bank refused\nwithout
giving a reason" would fail a plain substring test).

| metric | asks | sees wrong-chunk failures? |
|---|---|---|
| `hit@3` | right file fetched? | **no** |
| `ANSWER@3` | right text fetched? | **yes** |

## `python week4/measure.py --rerank` — zero API calls, 18 questions

    strategy                                ANSWER@3   hit@3  recall@3     MRR
    A  BASELINE dense only, chunk 600          0.667   0.889     0.861   0.796
    B  bm25 keyword only, chunk 600            0.722   0.833     0.833   0.769
    C  HYBRID dense+bm25 RRF, chunk 600        0.778   0.889     0.889   0.833
    D  dense only, chunk 1200                  0.722   0.889     0.861   0.796
    E  dense + cross-encoder rerank            0.833   0.889     0.889   0.861
    F  hybrid + rerank (2 changes)             0.889   0.944     0.944   0.889

**`hit@3` is 0.889 for A, C, D and E — completely flat.** Four materially
different systems, one identical score. The old metric could not tell them
apart. `ANSWER@3` ranges 0.667 to 0.833 across the same four.

### By question type (hit@3)

    strategy                       exact_code   mixed   semantic
    A  dense only                       0.857   1.000      0.875
    B  bm25 only                        1.000   0.667      0.750
    F  hybrid + rerank                  1.000   1.000      0.875

Dense scored 0.857 on exact codes — surprisingly high, because `ERR-4032` and
`ERR-4033` live in the *same file*, so confusing them costs nothing at document
granularity. **The metric was too coarse to expose a weakness already measured
in isolation (0.970 similarity in week 1).**

### Candidate single changes vs baseline A

    add BM25 + RRF fusion       ANSWER@3 0.667 -> 0.778 (+0.111)   MRR 0.796 -> 0.833
    raise chunk size to 1200    ANSWER@3 0.667 -> 0.722 (+0.056)   MRR 0.796 -> 0.796
    add cross-encoder rerank    ANSWER@3 0.667 -> 0.833 (+0.167)   MRR 0.796 -> 0.861

Each measured **alone**, so we know which one did what. Stacking hybrid AND
rerank (F) scores higher still, but that is two changes and is reported
separately so it is never mistaken for a single-change result.

## THE ONE CHANGE: dense + cross-encoder reranking

    ANSWER@3   0.667 -> 0.833   (+0.167)
    MRR        0.796 -> 0.861   (+0.065)
    hit@3      0.889 -> 0.889   (+0.000)

Retrieve 12 candidates with dense search, then a cross-encoder reads the
question and each chunk **together** and picks the best 3.

Chosen because the failure was a *ranking* failure, not a *coverage* failure —
the right chunk was already in the candidate pool, just outranked. A bi-encoder
cannot fix that because it never compares question and chunk directly.

## `python week4/recheck.py` — proof on the real answers (3 API calls)

    Q: Which decline codes cascade to the next acquirer, and which do not?
       (FAILED in week 3)
       chunks now retrieved:
         06_routing_cascading.md > Cascading              <-- now RANK 1
         06_routing_cascading.md > Observing the cascade
         08_refunds.md           > Refunds and cascading

       ANSWER: * Cascades (Soft declines):
                 * ERR-4032 insufficient funds [1]
                 * ERR-4033 issuer refused [1]
               * Does not cascade (Hard declines):
                 * ERR-4034 suspected fraud [1]
                 * ERR-4035 card expired [1]

Both questions that already passed still pass (ERR-4032 vs ERR-4033, and the
200-day refund). A change that fixes one thing and breaks two is a loss.

## FIXED by the change (3)

- Does ERR-4035 cascade to the next acquirer?
- What is ERR-4003?
- Which decline codes cascade, and which do not?   <- the original failure

## STILL BROKEN after the change (3)

    [exact_code] What does ERR-4092 mean?
        needed: 'ERR-4092'   got: 04_error_codes.md, 05_retries, 04_error_codes.md
    [semantic]   Why did my payment get rejected for being too small?
        needed: 'Amount below minimum'   got: 09_rate_limits, 08_refunds, 05_retries
    [mixed]      I got a timeout and don't know if the payment went through
        needed: 'idempotency_key'   got: 05_retries, 01_quickstart, 08_refunds

## `python week4/evidence_4092.py` — chunk and rank evidence

Exactly **one** chunk of 47 contains the string `ERR-4092`:

    chunk id : 08_refunds.md#1     section: Timing     length: 268 chars
    "Refunds on payments older than 180 days are rejected with ERR-4092.
     Issue a payout instead."

Note it lives in a section called *Timing* on the **refunds** page.
`04_error_codes.md` does not contain ERR-4092 at all.

    strategy                          rank (of 47)   score    top-K needed
    DENSE (week 3 + week 4 baseline)      28         0.1108      k >= 28
    BM25 keyword only                      1         7.2639      k >= 1
    HYBRID dense+bm25 RRF                 10         0.0278      k >= 10
    DENSE top-12 then RERANK        not in ranking     —         never

What dense fetched instead:

    1. 0.4078  03_payment_lifecycle.md  > Cancelling
    2. 0.3984  04_error_codes.md        > ERR-4032 vs ERR-4033
    3. 0.3958  04_error_codes.md        > 4xx — your request
    4. 0.3548  04_error_codes.md        > Error code reference
    ...
    28. 0.1108 08_refunds.md            > Timing            <- the answer

Three of the top five are the error-codes page. The embedding encodes "this is
an error-code question" and fetches the error-codes page — which doesn't have
this code. The gap is large (0.4078 vs 0.1108): dense is not marginally wrong.

### Why reranking could not save it

At rank 28 the chunk never enters the top-12 candidate pool, so the
cross-encoder never sees it.

> **A reranker can only reorder what retrieval already found.**

### Why hybrid also failed — the arithmetic

    RRF score = 1/(60 + rank_dense) + 1/(60 + rank_bm25)

    ERR-4092 chunk:  1/(60+28) + 1/(60+1) = 0.0114 + 0.0164 = 0.0278
    "4xx" chunk:     1/(60+3)  + 1/(60+5) = 0.0159 + 0.0154 = 0.0313   <- wins

BM25 ranked the right chunk **#1**. RRF demoted it to **#10**, because a chunk
both retrievers rank moderately beats a chunk one retriever ranks first. That is
RRF working as designed — *agreement beats conviction* — and here it is wrong.

Tuning tested:

    k       ERR-4092   wrong chunk   winner
    60        0.0278      0.0313     wrong
    30        0.0495      0.0589     wrong
    10        0.1172      0.1436     wrong
     5        0.1970      0.2250     wrong
     1        0.5345      0.4167     ERR-4092
     0        1.0357      0.5333     ERR-4092

    w_bm25=2  0.0442      0.0466     wrong
    w_bm25=3  0.0605      0.0620     wrong
    w_bm25=5  0.0933      0.0928     ERR-4092

Fixing it by tuning needs `k <= 1` or a **5x** BM25 weight — both extreme enough
to wreck the semantic questions.

**So the correct fix is structural, not a tuning knob:**
1. **Query routing** — detect `ERR-\d{4}` in the question and send it to BM25
   alone, bypassing fusion.
2. **Metadata filtering** — tag chunks with the codes they mention and filter
   before searching, turning it into a lookup rather than a similarity contest.

## Bug found and fixed

The BM25 tokenizer absorbed trailing punctuation: `ERR-4092.` in prose became
the token `err-4092.`, which never matched the query's `err-4092`. One character
silently broke exact-code matching. Found by testing BM25 **alone** before
fusing it.

## Mentor checklist

| check | result |
|---|---|
| show which failure kind, with evidence | cascade question — chunk text, scores and ranks |
| one change, not five | three candidates measured separately; winner is one change |
| a before-and-after number | ANSWER@3 0.667 -> 0.833, MRR 0.796 -> 0.861 |
| noticed what it did NOT fix | 3 failures, each with the reason reranking can't reach it |
