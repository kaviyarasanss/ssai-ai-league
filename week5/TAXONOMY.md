# Week 5 — Error analysis: open coding, taxonomy, ranking

Sample: 21 traces (`week5/traces.json`), app in BASELINE config
(dense-only retrieval, `all-MiniLM-L6-v2`, chunk 600 / overlap 100, k=3).

## Sampling — honest description

We have no real user traffic, so a true random sample is not available. These
21 questions are a **stratified** sample: exact_code (7), semantic (8),
mixed (3), out_of_scope (3). They were written to span question *types*, and
they deliberately include questions we already knew failed rather than
excluding them. The trap the brief warns about — keeping only the nice
examples — is the opposite of what was done here.

## Objective facts before any judgement

| fact | count |
|---|---|
| traces collected | 21 |
| answerable questions | 18 |
| answer text was actually retrieved | 12 / 18 |
| right document retrieved | 16 / 18 |
| app refused although the answer exists | **5 / 18** |
| answer carried a citation | 11 / 18 |
| out-of-scope correctly refused | 3 / 3 |
| **hallucinations** | **0** |

The gap between "right document 16" and "answer text 12" is four traces where
retrieval found the right file and still missed the answer.

## STEP 1 — Open coding: one honest note per problem trace

Written while reading, before any categories existed.

**T02 · What does ERR-4092 mean?** — Refused. Retrieval returned the generic
error-code sections and the payment-lifecycle page; none of them mentions
ERR-4092. The code is defined in a section called *Timing* on the **refunds**
page, which is not where a reader would look either.

**T04 · How should I back off when I receive ERR-4290?** — Answer is correct but
thin ("retry with exponential backoff") and omits the actual schedule from the
document. It wrote its markers as `[2, 3]`, and our citation parser only
matches `[2]`, so the answer shows **no source at all** despite citing two.

**T05 · Does ERR-4035 cascade?** — Refused. Two of three chunks are error-code
tables; the third is *Observing the cascade*, which is about `payment.attempts`,
not about which codes cascade. The chunk holding the soft/hard table never
appeared.

**T06 · What is ERR-4003?** — Refused. All three chunks came from the correct
file `04_error_codes.md`, but the retrieved slice of the long 4xx table does not
include the ERR-4003 row. The table was split by chunk size and we got the wrong
half.

**T08 · Which decline codes cascade, and which do not?** — Refused. All three
chunks from the correct file, but the third slot went to a 140-character overlap
fragment instead of the chunk containing the table.

**T15 · Why did my payment get rejected for being too small?** — Refused, and
retrieval was not close: quickstart, refunds, retries. The document says
"Amount below minimum (50 minor units)". Nothing in it says "too small".

**T17 · What happens if I use a sk_test_ key against live data?** — Answer is
correct and names ERR-4010, but markers are `[1, 3]` so the citation line is
empty again. Same defect as T04.

**T18 · I got a timeout and don't know if the payment went through.** — Answered
plausibly, but from the *quickstart* page's passing mention of timeouts rather
than the retries/idempotency page that actually explains idempotency keys. The
user is told to "use an idempotency key" and never told how, or that keys last
24 hours, or that they should derive from their own order ID.

## STEP 2 — Grouping those notes into named problems

**P1 · The answer is inside the right document but the chunk holding it loses
the ranking**
T05, T06, T08, T18 — 4 traces. Two distinct mechanisms, same outcome: a long
table gets split by `chunk_size` so the retrieved half lacks the needed row
(T06), or a short keyword-dense fragment outranks the long complete chunk (T08).

**P2 · Citations are dropped when the model groups markers as `[2, 3]`**
T04, T17 — 2 traces. Not a model failure. `rag.py` parses citations with
`re.findall(r"\[(\d+)\]", text)`, which matches `[2]` but not `[2, 3]`. Our bug.

**P3 · An exact identifier lives in an unexpected document**
T02 — 1 trace. `ERR-4092` appears once in the whole corpus, in a *Timing*
section on the refunds page. Every code-shaped question pulls the error-codes
page, which does not contain it.

**P4 · The user's words do not appear in the documents**
T15 — 1 trace. "too small" vs "Amount below minimum". Neither dense nor keyword
search bridges that gap.

## STEP 3 — Ranking by frequency x severity

Severity scale for a payments-documentation assistant:
- **3 = high**: user gets no usable answer, or an answer they cannot verify
- **2 = medium**: answer is usable but incomplete
- **1 = low**: cosmetic

| rank | problem | freq | severity | score | why this severity |
|---|---|---|---|---|---|
| **1** | **P1 chunk loses the answer** | 4/18 (22%) | 3 | **12** | Produced 3 of the 5 false refusals. The information exists, is indexed, and is still unreachable. |
| **2** | **P2 citations dropped** | 2/18 (11%) | 3 | **6** | The answer is right but unverifiable. "Every answer shows its source" is a stated requirement, and an uncited answer about retry policy is not safe to act on. |
| 3 | P3 identifier in an unexpected document | 1/18 (6%) | 3 | 3 | Refused here, so it failed safely — but the same retrieval could surface a *different* code's page and produce a confidently wrong answer. |
| 4 | P4 vocabulary gap | 1/18 (6%) | 2 | 2 | Users will phrase things their own way constantly; likely under-counted by our curated question set. |

**Note on severity that matters more than the ranking:** every single failure was
a refusal or an omission. **Zero hallucinations across 21 traces**, and 3/3
out-of-scope questions correctly refused. The app fails *silent*, not *wrong*.
For payments documentation that is the right direction to fail in — a confidently
wrong retry policy could cause a double charge; "I don't know" cannot.

## STEP 4 — Chosen fix target and prediction

**Target: P1** — highest frequency x severity, and it is the direct cause of most
false refusals.

**The fix:** cross-encoder reranking (retrieve 12 with dense, rerank to 3). Chosen
because P1 is a *ranking* failure — the right chunk is already in the candidate
pool, just outranked — and a bi-encoder cannot fix that, because it never
compares question and chunk directly.

### Prediction, written BEFORE measuring in week 6

1. P1: **3 of 4 fixed** (T05, T06, T08). T18 is uncertain — the quickstart
   mention is genuinely relevant, so a reranker may still prefer it.
2. P2: **not touched** by reranking. It is a regex in our own code. Fixing the
   pattern to `\[([\d,\s]+)\]` should take citation coverage from 11/18 to 13/18.
3. P3: **not fixed.** Already proven: dense ranks the ERR-4092 chunk 28th of 47,
   so it never enters the top-12 pool and the reranker never sees it.
4. P4: **not fixed.** Needs query rewriting or HyDE, not better ranking.
5. Overall answer-availability: **0.667 -> ~0.83**; false refusals **5 -> ~2**.

Week 6 turns each of these four problems into an automatic test and reports a
before/after score per problem type, so each line above is confirmed or refuted
with a number rather than an opinion.
