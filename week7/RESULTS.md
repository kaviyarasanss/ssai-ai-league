# Week 7 — Results

Two parts:

- **Part A — verification.** Runs with the network stubbed out, **zero API
  calls**, reproducible on any machine. Proves the control flow, budgets,
  memory and tool guards behave as designed.
- **Part B — the live race.** Real Gemini calls, real embeddings. This is
  where the interesting failure was found.

---

## Part A — Verification

### Method

The network dependencies are replaced with fakes injected into `sys.modules`
*before* `week7` imports anything:

| real dependency | replaced with | why |
|---|---|---|
| `llm.ask` | a scripted responder | exercises the loop without spending quota (20 req/day/model) |
| `sentence_transformers` | hashed bag-of-words bi-encoder + overlap cross-encoder | no HuggingFace download |
| `rank_bm25.BM25Okapi` | a real BM25 implementation (~25 lines) | keyword lookup is genuinely exercised, not faked away |

Everything else is the **real code**: real documents, real chunking
(600/100), real BM25 scoring, real retrieval, real agent loop, real
`race.py`.

### A1 — Control flow and budgets

| scenario | expected | observed | ✔ |
|---|---|---|---|
| normal | `completed` | `completed` | ✔ |
| repeat guard | stop as stuck | `repeated the same action twice - stuck`, 2 steps | ✔ |
| malformed reply (prose, non-empty) | stop immediately | `model reply was malformed (no ACTION and no FINAL)`, 1 step | ✔ |
| **empty reply, then a good one** | retry and recover | retried at 2× budget, run **completed**, 3 steps / 4 calls | ✔ |
| **empty reply every time** | one retry, then stop | `model returned an empty reply - output budget consumed by thinking tokens`, 2 calls | ✔ |
| **empty reply with no call budget left** | do not waste a retry | stopped at **1 call** | ✔ |
| step budget | stop at cap | `step budget exceeded (3 steps)` | ✔ |
| call budget | stop at cap | `call budget exceeded (3 calls)` | ✔ |
| time budget | stop before spending | `time budget exceeded (0.0s)`, **0 steps, 0 calls** | ✔ |
| hallucinated tool name | recoverable message | `No tool named 'grep_docs'. Available: search_docs, lookup_error_code.` | ✔ |

The time-budget row is the one to point at: **0 calls**. Budgets are checked
at the *top* of the loop body, so we never pay for the call that breaks the
budget.

The three empty-reply rows were added **after** the first live race, which is
what found the bug. See Part B.

### A2 — Memory

| check | observed |
|---|---|
| summarisation fires past 6 scratchpad entries | `[memory] compressed older steps` at steps 7 and 9 |
| run survives compression | yes — continued to the step cap |
| compression calls are counted | **10 steps → 12 `llm_calls`** |

If the compression calls weren't counted, the agent-vs-workflow cost
comparison would understate the agent.

### A3 — Tool guards

| input | returned |
|---|---|
| `ERR-4092` | `[08_refunds.md > Timing]` — the chunk dense search ranks **28th of 47** |
| ` err-4033 ` (padded, lowercase) | `[04_error_codes.md > ERR-4032 vs ERR-4033]` — normalised, found |
| `4092` (no prefix) | `'4092' is not a valid error code. Expected the form ERR-4032…` |
| `ERR-9999` (not in corpus) | `ERR-9999 is not mentioned anywhere in the documentation.` |
| prose via `search_docs` | `[09_rate_limits.md > Reducing usage]` |

The `ERR-9999` row is the important guard: BM25 returns its top 3 whether or
not any contain the code, so without the exact-containment filter the agent
would confidently answer about the **wrong code**.

### A4 — Quota protection

| check | observed |
|---|---|
| finished question checkpointed | yes, after every question |
| re-run skips finished questions | `Q1..Q4: already in race_results.json - skipping` |
| cost of the re-run | **0 LLM calls**, scoreboard rebuilt from disk |
| quota `SystemExit` | caught; partial scoreboard printed instead of the run being lost |

---

## Part B — The live race (run 1)

`python week7\race.py` · model `gemini-3.5-flash-lite` · 12 requests spent.

### Scoreboard

| | AGENT | WORKFLOW |
|---|---|---|
| reliability | **2/4** | **2/4** |
| LLM calls | 8 | 4 |
| total seconds | 25.7 | 7.4 |
| total steps | 8 | 15 |

### Per question

| Q | required facts | agent | workflow |
|---|---|---|---|
| 1 — ERR-4033 retry + cascade | `refused`, `cascade` | **PASS** · 3 calls · 17.5s | **PASS** · 1 call · 2.4s |
| 2 — ERR-4092 refund | `180 days`, `payout` | **PASS** · 2 calls · 3.2s | **PASS** · 1 call · 1.5s |
| 3 — timeout retry | `idempotency`, `24 hours` | **FAIL** — *empty model reply* | **FAIL** — missing `24 hours` |
| 4 — ERR-4290 backoff | `retry`, `jitter` | **FAIL** — *empty model reply* | **FAIL** — missing `jitter` |

### The finding: the agent died of an empty reply, not a bad answer

Both agent failures stopped with
`stop_reason: "model reply was malformed (no ACTION and no FINAL)"`, and the
recorded `raw` field for those steps is an **empty string**. The model
returned nothing at all.

**Root cause.** `max_output_tokens` caps *visible* output and *hidden
thinking tokens* together. The agent was calling `ask(..., max_tokens=700)`.
On the harder questions — Q4's second turn followed a long observation — the
model spent the entire 700 on thinking and emitted no visible text.

This is **week 1's finding resurfacing as a control-flow bug**: week 1
established that hidden thinking tokens are real and are why `temperature=0`
isn't reproducible on this model. Here the same tokens silently consume an
output budget and kill an agent turn.

Note what did **not** happen: the loop did not hang, retry forever, or
produce a confident wrong answer. It detected the unusable reply, stopped,
and recorded why. The safety machinery worked — it just had nothing to work
with.

**Fix applied (`week7/agent.py`).**

1. `REPLY_TOKENS = 2000`, named and commented, replacing the inline `700`.
2. An empty reply is no longer treated as "malformed". It gets **one** retry
   at double the budget with an explicit format reminder, and only then stops
   — with its own distinct `stop_reason` so the two failure modes are never
   confused again. The retry is skipped when the call budget is exhausted, so
   the fix cannot blow the cost cap.

Both paths are verified in Part A (rows 4–6).

### The workflow's failures are a different problem

Q3 missed `24 hours` and Q4 missed `jitter`. Neither is a format bug — the
facts live in a **different chunk of the same file** from the one retrieved:

- `jitter` is in *"Recommended backoff"*; the retrieved chunk was *"Which
  errors to retry"*
- `24 hours` (idempotency key lifetime) is in a different section from the
  timeout advice

The fixed workflow does exactly one search and cannot notice the gap. **This
is precisely the case an agent is supposed to win** — see a partial answer,
issue a second refined search. Run 1 could not test that, because the agent
never got to reply on those two questions.

### Prediction for run 2, written now

1. **Q1 and Q2 stay PASS in both.** They already work and nothing about
   their path changed.
2. **The agent now reaches a FINAL on Q3 and Q4.** The empty-reply retry
   plus the larger budget removes the failure mode entirely.
3. **The open question — the one worth running for — is whether the agent
   then gets `jitter` and `24 hours`.** If it issues a second refined search
   after seeing an incomplete first result, it beats the workflow **3–4/4 to
   2/4**, and that is the whole argument for paying 2–3× the calls. If it
   answers from the first observation anyway, it ties at 2/4 and the honest
   conclusion is that this task never needed an agent.

Run 2 costs a fresh ~14 requests, so it needs a new day's quota:

```
python week7\race.py --fresh
```

### What I got wrong in run 1

I predicted Q4 would be decided by *retrieval* — whether the agent searched
twice. It was actually decided by *infrastructure*: an output-token budget
that was too small for a thinking model. **The experiment I designed could
not have answered the question I asked, and only running it showed that.**
That is the same lesson as week 6's one-sided refusal guard: an unfair or
broken comparison does not announce itself.

---

## Recommendation for the hand-over

**Ship the fixed workflow**, on the evidence so far: 1 LLM call per question
versus 2–3, roughly 3× faster (7.4s vs 25.7s total), identical reliability at
2/4, and it structurally cannot loop because there is no loop.

That recommendation is **provisional on run 2**. The one scenario that would
overturn it is the agent recovering `jitter`/`24 hours` with a second search —
a capability the fixed sequence cannot have at any price. Nothing else in
this data set justifies the agent's cost.
