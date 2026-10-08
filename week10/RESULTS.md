# Week 10 — Results

Single agent (2 tools) **vs** squad (manager + 2 one-tool specialists), on the
same questions from `week7/race.py`.

---

## Live run — Q1 complete

```
Q1: A payment failed with ERR-4033. Should I retry the same card,
    and will it cascade to another acquirer?
    required facts: ['refused', 'cascade']
```

| | SINGLE | SQUAD | squad / single |
|---|---|---|---|
| **quality** | **FAIL** — missing `cascade` | **PASS** | — |
| **LLM calls** | 2 | 6 | **3.0×** |
| **tokens (work)** | 1,220 | 2,059 | **1.7×** |
| **wall-clock** | 3.71 s | 20.72 s | **5.6×** |
| **cost (USD)** | $0.000170 | $0.000321 | **1.9×** |

### Why the squad won — the mechanism, not a guess

The single agent looked up `ERR-4033`, got the error-code chunk, and
**answered immediately**. It never searched for the cascade policy, which
lives in a *different document* (`06_routing_cascading.md`).

That is exactly Week 8's **`SKIPPED_STEP`** failure, reproducing live.

The squad structurally could not make that mistake. The manager split the
question into two tasks, so `policy_specialist` was *forced* to run
`search_docs('retry card cascade acquirer')` and found the cascade rule.

> The squad did not win by being smarter. It won because **splitting the
> question forced a second lookup the single agent skipped** — and it paid
> 3× the calls and 5.6× the wall-clock for that.

This is the same finding as Week 8's required-step gate, reached by a
different route: the gate *forces* the missing step inside one agent; the
squad *structures it away* across three. The gate cost +6 calls across four
questions. The squad cost +4 calls on one.

---

## Q2–Q4: stopped by the free-tier quota

The run hit the **20 requests/day/model** cap during Q2's compose call, after
four exponential-backoff retries on `429 RESOURCE_EXHAUSTED`.

**That is itself a measured result, not just an inconvenience:**

> A 3-agent squad burns a fixed daily quota about **3× faster** than one
> agent. On a free tier, that means **a third as many experiments per day**.
> Cost per question is the number people quote; experiments per day is the
> one that decides how fast you can learn.

Q1 is checkpointed in `race_results.json`, so re-running resumes at Q2
without repeating it:

```
python week10/race.py
```

---

## Fairness — mentor check 1

Same question, same required facts, same tools, same index, same model, same
process, same meter. **The only variable is the control flow.**

The single agent runs through the *same* meter (`race.py` wraps
`week7.agent.ask`), so the token figures are directly comparable rather than
two separate measurements compared by eye. Week 6's one-sided refusal guard
is why this is stated explicitly.

## Tokens — mentor check 2

A cached call reports **zero** tokens, so every call is counted twice:

| | |
|---|---|
| **work** | ~4 chars/token on prompt + reply, cache-independent |
| **billed** | what the API charged; cache hits are 0 |

The race is decided on **work** — the real conversation size each design
needs, i.e. what production pays on a cold cache. Deciding on `billed` would
let cache luck pick the winner.

## Verdict — mentor check 3

**On the evidence so far: this is not a clean win for either side.**

The squad bought a correct answer that the single agent missed — and that is
the only thing a user actually cares about. But it paid **3× the calls, 1.9×
the cost and 5.6× the wall-clock** for one question, and 5.6× latency is a
product-level problem, not a rounding error.

**What I would actually ship:** the single agent **with Week 8's
required-step gate**. It buys the same forced second lookup for roughly +1
call rather than +4, with no manager and no compose step. The squad is the
expensive way to fix a problem Week 8 already fixed cheaply.

**What would change my mind:** running the specialists **in parallel**. The
squad's 5.6× latency is almost entirely sequential hand-offs. In parallel it
would not use fewer tokens, but the wall-clock gap would largely close — and
that is the one axis where a squad can genuinely beat one agent. Untested
here, and I would not claim it without the number.

## When multi-agent would be worth it — mentor check 4

- parts **genuinely independent and parallel**, so tokens buy wall-clock back
- sub-jobs needing **clearly different instructions**, too long for one prompt
- a specialist needing **different permissions** — one write, one read-only
- sub-jobs wanting **different models**, cheap for the easy half

**Not worth it for:** a pipeline you could write in advance (week 7),
sub-tasks that depend on each other and serialise anyway, or anything one
agent already passes.

## Honest limits

- **One question raced live.** A 3× cost ratio on one question is a real
  measurement; a quality verdict on one question is not. Q2–Q4 are pending
  quota.
- **Specialists ran sequentially.** The axis where a squad could win is
  untested.
- **One squad shape** — the one the brief describes.
- The stub-model dry run predicted a **tie** on quality. The live run
  disagreed on the very first question. Same lesson as week 7: a stub tests
  the plumbing, not the model.
