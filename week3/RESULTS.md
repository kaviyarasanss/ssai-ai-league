# Week 3 — what we ran, what came out, what it meant

Config: `chunk_size=600, overlap=100, k=3`, model `gemini-3.5-flash-lite`,
10 documents -> **47 chunks**.

## `python week3/ask.py` — 7 questions, 7 API calls

### Correct answers (4 of 5 answerable)

    Q: What is the difference between ERR-4032 and ERR-4033?
    A: ERR-4032 means the customer has insufficient funds... retrying the same
       card later may succeed [1]. ERR-4033 means the issuing bank refused
       without giving a reason... route to an alternative payment method [1].
       sources: 04_error_codes.md > ERR-4032 vs ERR-4033
       retrieved: 0.682 04_error_codes.md > ERR-4032 vs ERR-4033
                  0.410 02_authentication.md > Restricted keys
                  0.379 04_error_codes.md > 4xx — your request

    Q: How long are idempotency keys stored, and what should I derive one from?
    A: Stored for 24 hours [2]. Use something derived from your own order ID,
       rather than a random UUID generated at call time [2].

    Q: What happens if my webhook endpoint does not respond in time?
    A: Must return 2xx within 5 seconds [2]; otherwise treated as a failure and
       retried: 10s, 1m, 10m, 1h, 6h, 24h [1], then marked `undelivered` [1].

    Q: Can I refund a payment that is 200 days old?
    A: No — refunds on payments older than 180 days are rejected with ERR-4092;
       issue a payout instead [1].

### Correct refusals (2 of 2 out-of-scope)

    Q: What is the SDK's monthly pricing for the Enterprise plan?
    A: I don't know - that is not covered in the documentation.
       retrieved top score 0.404

    Q: How do I integrate PhoenixPay with Salesforce?
    A: I don't know - that is not covered in the documentation.
       retrieved top score 0.721   <-- HIGH score, still no answer present

> **0.721 is higher than the ERR-4032 question that answered correctly (0.682).**
> A high similarity score does not mean the answer is there. Similarity measures
> *topic*, not *containment*. This is why the prompt-level refusal instruction
> matters more than the score threshold.

### The one failure

    Q: Which decline codes cascade to the next acquirer, and which do not?
    A: I don't know - that is not covered in the documentation.        <-- WRONG
       retrieved: 0.522 06_routing_cascading.md > Payment routing and cascading
                  0.516 06_routing_cascading.md > Observing the cascade
                  0.496 06_routing_cascading.md > Cascading

All three chunks came from the **correct file**. So not "wrong document".

    [models/gemini-3.5-flash-lite]  api_calls=7  in=2544 tok  out=297 tok

## `python week3/ask.py --chunks` — zero API calls

Probe: *"Which decline codes cascade to the next acquirer?"*

    chunk_size=300   overlap=60   -> 62 chunks
        0.535 06_routing_cascading.md  ## Observing the cascade...
        0.524 06_routing_cascading.md  soft** declines cascade. Hard declines... |Code|Type
        0.519 06_routing_cascading.md  # Payment routing and cascading...

    chunk_size=600   overlap=100  -> 47 chunks
        0.535 06_routing_cascading.md  ## Observing the cascade...
        0.519 06_routing_cascading.md  # Payment routing and cascading...
        0.499 06_routing_cascading.md  No | Cascading a hard decline is a compliance risk...

    chunk_size=1200  overlap=200  -> 44 chunks
        0.535 06_routing_cascading.md  ## Observing the cascade...
        0.519 06_routing_cascading.md  # Payment routing and cascading...
        0.433 06_routing_cascading.md  ## Cascading When enabled, a soft decline...  <-- FULL TABLE

**Ranks 1 and 2 never change** — those sections already fit under every chunk
size, so chunking doesn't touch them. Only slot 3 moves.

## Root cause of the failure — traced to the character

The `## Cascading` section is **640 characters**. At `chunk_size=600` it is cut:

    char:  0                                    500      600   640
           [========== chunk A: 0-600 ==============]
                                                 [== chunk B: 500-640 ==]
                                                  ^ starts 100 early = the overlap

    chunk A (600 chars)  ## Cascading + code example + THE FULL TABLE
    chunk B (140 chars)  "No | Cascading a hard decline is a compliance risk..."
                         no table, no codes, no answer

    chunk B scored 0.499   -> made the top 3
    chunk A scored ~0.433  -> did NOT

**Why the useless chunk won:** cosine similarity measures direction, and a short
chunk has a concentrated direction. Chunk B is 140 characters almost entirely
about cascading. Chunk A averages a heading, a code block, prose and a table, so
its vector is diluted.

> **Short and shallow beat long and correct.**

At `chunk_size=1200` the 640-char section is under the limit, so chunk B never
exists and chunk A reaches the model — at a *lower* score (0.433 vs 0.499)
because the bigger chunk dilutes the vector. **Bigger chunks cost precision and
buy completeness.**

### The failure category

Not "wrong document" and not "bad prompt" — a third kind:

| | Retrieval | **Chunking/ranking** | Generation |
|---|---|---|---|
| right doc fetched? | no | **yes** | yes |
| answer intact in prompt? | — | **no** | yes |
| fix | search | **chunk size / reranking** | prompt |

An initial diagnosis — "the table was sliced by the boundary" — was **wrong**;
dumping the chunk text showed the table intact in chunk A. The real cause was the
overlap fragment outranking it. Recorded because the correction matters more than
the first guess.

## Mentor checklist

| check | result |
|---|---|
| answers correctly from the documents | 4/5 answerable, with citations |
| every answer shows its source | yes — `sources:` line, parsed from `[n]` markers |
| admits when it doesn't know | 2/2 out-of-scope refused |
| tried more than one chunk size | 300 / 600 / 1200 compared, difference explained |
