# Week 1 — what we ran, what came out, what it meant

## `01_tokens.py` — tokenisation and cost

    text   : 'The payment failed.'      chars: 19  words: 3  TOKENS: 4
      pieces : ['The', ' payment', ' failed', '.']
    text   : 'unbelievable'             chars: 12  words: 1  TOKENS: 3
      pieces : ['un', 'belie', 'vable']
    text   : 'idempotency'              chars: 11  words: 1  TOKENS: 4
      pieces : ['id', 'emp', 'ot', 'ency']
    text   : 'ORD-4471-XZ'              chars: 11  words: 1  TOKENS: 6
      pieces : ['ORD', '-', '447', '1', '-X', 'Z']
    text   : '{"status": "settled", "amount": 1499}'  chars: 37  TOKENS: 14
    text   : 'payment failed'           chars: 14  words: 2  TOKENS: 2
    text   : 'பணம் செலுத்துதல் தோல்வி'   chars: 23  words: 3  TOKENS: 33

| sample | chars/token | vs English |
|---|---|---|
| `payment failed` | 7.0 | baseline |
| JSON | 2.6 | 2.7x worse |
| `ORD-4471-XZ` | 1.8 | 3.8x worse |
| Tamil | 0.7 | 10x worse |

**Observations**
- `"The payment failed."` is 3 words but **4 tokens** — the `.` is its own token.
  "1 token = 1 word" is wrong in both directions.
- `ORD-4471-XZ` becomes `['ORD','-','447','1','-X','Z']`. The model never sees
  `4471` as one thing. This is why LLMs are unreliable on exact identifiers, and
  it is the reason week 4 adds keyword search.
- Tamil token pieces are broken fragments (`'�'`) — a single character is
  split across several tokens, hence ~10x the cost per character.

## `02_temperature.py` — temperature 0 is not reproducible

On `gemini-3.6-flash`, three temperature-0 calls with the same prompt:

    run 1: The transaction failed when the customer's credit card was unexpectedly declined at checkout.
    run 2: The transaction was declined due to insufficient funds.
    run 3: The transaction failed after the credit card was abruptly declined.
    --> all identical? False

**Prediction was "identical". It was wrong.** Cause: the model generates hidden
*thinking* tokens before answering, and that reasoning is itself sampled.

**Corrected rule:** reproducibility needs `temperature=0` **and a fixed `seed`**.

### A cache bug that invalidated a run

The first re-run showed `all identical? True` — but `api_calls=5` when 11 were
expected. The disk cache was serving runs 2 and 3 from the previous answer, so
"identical" proved nothing. Fixed by passing `use_cache=False` wherever the
thing being measured *is* variation.

> A cache is correct for saving quota and wrong when measuring variation.

## `03_temperature_open.py` — temperature can be invisible

    CLOSED  "describe a payment that failed"    temp 1.8, 2 runs -> 1 unique
    OPEN    "invent a name for a coffee shop"   temp 0.0, 2 runs -> 1 unique
    OPEN    "invent a name for a coffee shop"   temp 1.8, 3 runs -> 1 unique
                                                 ("Velvet Bean" every time)

Prediction: the open question would vary at temp 1.8. **Wrong again.**

## `04_why_no_variation.py` — isolating why

Four hypotheses, each with a test:

    H1  temp=2.0, top_p=1.0, top_k=200   -> "Velvet Bean" x3   (top_p was not the filter)
    H2  seed=1 -> Velvet Bean
        seed=500 -> Velvet Bean
        seed=99999 -> Lunar Roast        -> VARIES: sampling IS happening
    H4  same test on gemini-3.8-flash    -> The Roasted Quill / Copper & Crema /
                                            Velvet & Vapour   -> VARIES

**Conclusion:** `flash-lite` does sample, but its output distribution is far
more *peaked* than `3.8-flash`'s. Flattening a very tall spike still leaves a
spike. Small distilled models are more confident — which is also why they are
worse at admitting they don't know.

> Temperature widens the net; it does not add fish.

## `05_embeddings.py` — local, zero API calls

    'The payment failed.' -> vector of 384 numbers

### Meaning vs keywords — this one FAILED

    question: 'How do I get my money back?'
    sim=0.409  words in common: 0   "Refunds are issued to the original card within 5 business days."
    sim=0.509  words in common: 2   "Please put the money back in the petty cash box."   <-- WON
    sim=0.192  words in common: 1   "Our office is located on Back Street."

The wrong document won. The phrase "money back" dragged a distractor to the top.
Cause: a **bi-encoder** compresses each text into one vector independently, so it
never compares the question and the document against each other. That gap is
exactly what a cross-encoder reranker fills (week 4).

### Where embeddings fail on identifiers

    sim=0.970   'ERR-4032' vs 'ERR-4033'
    sim=0.500   'ERR-4032' vs 'ERR-9999'
    sim=0.996   'invoice INV-2024-881' vs 'invoice INV-2024-882'

Embeddings encode "looks like an error code", not *which* code.

### Static vs contextual — this one WORKED

    A: The bank declined the charge on my card.
    B: We charge the battery overnight before the trip.
    C: The issuer rejected the transaction on my credit card.

    A vs B  sim=0.211   (both contain "charge")
    A vs C  sim=0.693   (no shared keyword at all)

Shared keyword scored low, shared meaning scored high. Word2Vec/GloVe are static
(one fixed vector per word) and would have put A near B.

## `00_quota.py` — the constraint that shaped everything

    quotaId    : GenerateRequestsPerDayPerProjectPerModel-FreeTier
    quotaValue : 20
    model      : gemini-3.6-flash

    WORKS   models/gemini-3.8-flash
    WORKS   models/gemini-3.5-flash
    WORKS   models/gemini-3.5-flash-lite
    WORKS   models/gemini-3.1-flash-lite
    BLOCKED models/gemini-2.5-flash-lite  -> 404 NOT_FOUND
    BLOCKED models/gemini-3.6-flash       -> 429, 20/day exhausted

**20 requests per day, PER MODEL.** Consequences, all implemented in `llm.py`:
- pin the model in `.env` (never a `-latest` alias — week 6 compares before/after
  scores and a silent upgrade makes them incomparable)
- split by job: `gemini-3.5-flash-lite` as workhorse, `gemini-3.8-flash` reserved
  for week 6 judging — two models means two separate daily quotas
- cache every response to disk, keyed on a hash of everything that affects the
  answer, so re-running an eval to fix a typo costs nothing

## Errors met, and what each taught

| error | meaning | retry? |
|---|---|---|
| `404 NOT_FOUND` | `gemini-2.5-flash` retired for new users | no — change the model |
| `400 INVALID_ARGUMENT` | `thinking_budget=0` is refused by this model; `thinking_level='low'` is accepted | no — fix the request |
| `429 RESOURCE_EXHAUSTED` | daily quota spent | yes, with backoff |
| `503 UNAVAILABLE` | Google's servers busy | yes, with backoff |

The 400 was opaque ("Request contains an invalid argument" — no field named), so
`00_diagnose.py` **bisects** the request: send it repeatedly, adding one argument
at a time, and the first FAIL is the culprit. Cheapest and simplest tests first,
so an unrelated late failure can't be mistaken for an early cause — the 429 landed
on the last test and would otherwise have been blamed on high temperature.
