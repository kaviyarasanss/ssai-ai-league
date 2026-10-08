# Week 10 — Results

Single agent (2 tools) **vs** squad (manager + 2 one-tool specialists), on the
same four questions from `week7/race.py`.

Raw data: `week10/race_results.json` (all 4 questions, checkpointed).

---

## Live run — all 4 questions

| | SINGLE | SQUAD | squad / single |
|---|---|---|---|
| **quality** | **2 / 4** | **4 / 4** | — |
| **LLM calls** | 9 | 22 | **2.44×** |
| **tokens (work)** | 4,830 | 6,697 | **1.39×** |
| **tokens (billed)** | 5,412 | 7,461 | 1.38× |
| **wall-clock** | 18.20 s | 83.14 s | **4.57×** |
| **cost (USD)** | $0.000653 | $0.001030 | **1.58×** |

### Per question

| # | question | single | squad |
|---|---|---|---|
| Q1 | `ERR-4033` — retry same card? cascade? | **FAIL** — missing `cascade` · 2 calls · 1,220 tok · 3.71 s | PASS · 6 calls · 2,059 tok · 20.72 s |
| Q2 | `ERR-4092` — refund rejected | PASS · 3 calls · 1,327 tok · 6.16 s | PASS · 6 calls · 1,587 tok · 42.64 s |
| Q3 | request timed out — what to send on retry | PASS · 2 calls · 1,208 tok · 4.01 s | PASS · 4 calls · 1,253 tok · 7.36 s |
| Q4 | `ERR-4290` — retryable? what backoff? | **FAIL** — missing `jitter` · 2 calls · 1,075 tok · 4.32 s | PASS · 6 calls · 1,798 tok · 12.42 s |

---

## Why the squad won — the mechanism, not a guess

Both single-agent failures are the **same failure**, and it is a *trajectory*
failure, not a knowledge failure.

On **Q1** and **Q4** the single agent called `lookup_error_code`, got the
error-code chunk, and **answered immediately**. It never called `search_docs`.
The missing fact in each case lives in a *different document*:

- Q1 — the cascade rule is in `06_routing_cascading.md`, not `04_error_codes.md`
- Q4 — the jitter requirement is in `05_retries_idempotency.md`, not the code table

That is exactly Week 8's **`SKIPPED_STEP`**, reproducing live on 2 of 4
questions.

The squad structurally could not make that mistake. The manager split each
question into a CODE_TASK and a POLICY_TASK, so `policy_specialist` was
*forced* to run `search_docs` — on Q1, Q2 and Q4 — and it found the missing
rule every time. On Q3 the manager correctly issued only a POLICY_TASK (one
specialist, 4 calls), which is why Q3 is the cheapest squad run.

> The squad did not win by being smarter. It won because **splitting the
> question forced a second lookup the single agent skipped** — and it paid
> 2.44× the calls and 4.57× the wall-clock for that.

Same finding as Week 8's required-step gate, reached by a different route: the
gate *forces* the missing step inside one agent; the squad *structures it away*
across three.

---

## Fairness — mentor check 1

Same questions, same required facts, same tools, same index, same model, same
process, same meter. **The only variable is the control flow.**

The single agent runs through the *same* meter (`race.py` wraps
`week7.agent.ask`), so the token figures are directly comparable rather than
two separate measurements compared by eye. Week 6's one-sided refusal guard is
why this is stated explicitly.

## Tokens — mentor check 2

A cached call reports **zero** tokens, so every call is counted twice:

| | |
|---|---|
| **work** | ~4 chars/token on prompt + reply, cache-independent |
| **billed** | what the API charged; cache hits are 0 |

The race is decided on **work** — the real conversation size each design needs,
i.e. what production pays on a cold cache. Deciding on `billed` would let cache
luck pick the winner. Here they agree (1.39× vs 1.38×), which is itself worth
stating: the cache did not decide this race.

**Why tokens (1.39×) grew so much less than calls (2.44×).** Each specialist
carries a *short* prompt — one tool, one sub-task — while the single agent
re-sends its whole scratchpad every turn. More agents did not mean
proportionally more context.

## Verdict — mentor check 3

**The squad won on the only axis a user feels: 4/4 vs 2/4.** At 1.58× cost that
is cheap. At **4.57× wall-clock** it is not — 83 s for four questions is a
product-level problem, not a rounding error.

**What I would actually ship:** the single agent **with Week 8's required-step
gate**. It buys the same forced second lookup — the exact thing that won this
race — for roughly **+1 call per question** instead of the squad's +13 calls
total, with no manager and no compose step. Week 8 measured that gate taking
trajectory score from 0.250 to 1.000 for +6 calls across the same four
questions. The squad is the expensive way to fix a problem Week 8 already fixed
cheaply.

**What would change my mind:** running the specialists **in parallel**. The
4.57× latency is almost entirely sequential hand-offs. In parallel it would not
use fewer tokens, but the wall-clock gap would largely close — and that is the
one axis where a squad can genuinely beat one agent. Untested here, and I would
not claim it without the number.

## Quota — a measured operational finding

The first attempt at this race hit the free tier's **20 requests/day/model**
cap during Q2, after four exponential-backoff retries on
`429 RESOURCE_EXHAUSTED`. The checkpoint in `race_results.json` let the rerun
resume at Q2 instead of repeating Q1.

> A 3-agent squad burns a fixed daily quota ~2.4× faster than one agent. On a
> free tier that means **a fraction as many experiments per day**. Cost per
> question is the number people quote; experiments per day is the one that
> decides how fast you can learn.

## When multi-agent would be worth it — mentor check 4

- parts **genuinely independent and parallel**, so tokens buy wall-clock back
- sub-jobs needing **clearly different instructions**, too long for one prompt
- a specialist needing **different permissions** — one write, one read-only
- sub-jobs wanting **different models**, cheap for the easy half

**Not worth it for:** a pipeline you could write in advance (week 7), sub-tasks
that depend on each other and serialise anyway, or anything one agent already
passes — Q3 is the live example: the squad spent 2× the calls to reach the same
PASS.

## Honest limits

- **Four questions, one run each.** A 2/4-vs-4/4 split on four questions is a
  real signal, not a statistic. No repeats, no variance estimate.
- **Specialists ran sequentially.** The axis where a squad could win is
  untested.
- **One squad shape** — the one the brief describes. No debate, no critic, no
  retry-on-failure.
- The stub-model dry run predicted a **tie** on quality. The live run
  disagreed on two questions. Same lesson as week 7: a stub tests the plumbing,
  not the model.
- Q2's squad run took **42.64 s** — over half the squad's total wall-clock —
  which is backoff noise, not design cost. The latency ratio is therefore a
  pessimistic read of the squad.
