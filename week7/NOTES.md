# Week 7 — Agent Loops

Track E (developer documentation). Same PhoenixPay SDK corpus as weeks 3–6,
same index, same `llm.py` client. What is new this week is **control flow**.

---

## 1. What an agent actually is

Weeks 3–6 were a **pipeline**: retrieve → prompt → answer. One shape, always.

An agent is a **loop** where the model decides what happens next:

```
while not done:
    THOUGHT      the model says why it is doing the next thing
    ACTION       the model names a tool and its input
    OBSERVATION  OUR CODE runs the tool and pastes the result back
FINAL            the model answers
```

That pattern has a name: **ReAct** (Reason + Act). Reason, act, observe, repeat.

**The single most important rule: the model never runs anything.** It emits
text that names a tool. Our code parses that text, calls the function, and
feeds the result back as the next message. Same as week 2 tool calling — the
difference is that this week we drive the loop ourselves instead of letting
the SDK hide it, so every step is visible.

Why bother? Because the path is **data-dependent**. "ERR-4092 on a refund,
what do I do?" needs: look up the code → discover it is a refund-window
problem → then look up the refund policy. Step 2 is only knowable *after*
step 1 returns. A fixed pipeline cannot express that.

---

## 2. Tool design — the part people underrate

The model chooses a tool by reading its **description** and nothing else. Not
the function name, not the code, not your intentions. A vague description is
the #1 cause of an agent picking the wrong tool.

So every description in `tools.py` states three things:

| | |
|---|---|
| **what it does** | one line |
| **USE FOR** | the cases it is right for |
| **DO NOT USE FOR** | the cases it is wrong for |

We gave the agent exactly **two** tools, deliberately complementary — the
same dense/sparse split we measured in weeks 1 and 4:

| tool | mechanism | strength | measured weakness |
|---|---|---|---|
| `search_docs` | dense embeddings + cross-encoder rerank | prose questions — "how do I stop fake webhooks" | ERR-4032 vs ERR-4033 embed at **0.970** cosine → cannot tell codes apart |
| `lookup_error_code` | BM25 exact keyword | one specific `ERR-####` | useless for prose |

`lookup_error_code` is the **structural fix for problem P3** from week 5:
ERR-4092 lives on the refunds page, and dense search ranked that chunk
**28th of 47**. Week 6 proved reranking could not reach it — a reranker can
only reorder what retrieval already handed it. Giving the model a keyword
tool fixes it properly.

One extra guard in that tool, and it matters:

```python
hits  = retrieval.bm25_search(code, _CHUNKS, _BM25, k=3)
exact = [h for h in hits if code in h["text"]]      # <- the P3 fix
if not exact:
    return f"{code} is not mentioned anywhere in the documentation."
```

BM25 returns its top 3 whether or not any of them actually contain the code.
Without that filter the agent gets a near-miss chunk and confidently answers
about the **wrong code**. Better to say "not mentioned" than to be wrong.

Two other cheap guards:
- `re.fullmatch(r"ERR-\d{3,4}", code)` — bad input gets a *helpful* message
  ("expected the form ERR-4032. Use search_docs for prose questions."), not a
  crash. The error message is part of the tool's interface.
- `run_tool()` on an unknown name returns
  `"No tool named 'grep_docs'. Available: search_docs, lookup_error_code."` —
  the model can recover from that. A traceback it cannot.

`init()` builds the index **once** and both racers share it, so the race
compares two control flows, not two different indexes.

---

## 3. Stop conditions and budgets

An agent without budgets can loop forever and bill you for it. We enforce
**four**, and all four are tested:

| budget | value | what it catches |
|---|---|---|
| `max_steps` | 6 | model that never says FINAL |
| `max_seconds` | 90 | slow tools / hanging call |
| `max_calls` | 8 | cost cap, counted including memory calls |
| repeat guard | — | same action + same input twice in a row = stuck |

Two design details worth defending:

**Budgets are checked *before* spending, not after.** The check sits at the
top of the loop body, so we never pay for the call that breaks the budget.

**`stop_reason` is returned in the trace, always.** Not printed — returned.
`"completed"`, `"repeated the same action twice - stuck"`, `"step budget
exceeded (6 steps)"`, `"model reply was malformed (no ACTION and no FINAL)"`.
An agent that stops is fine; an agent that stops *silently* is not
debuggable. This is the week-5 tracing lesson applied to control flow.

The `for ... else` at the bottom is the Python detail that makes the step
budget honest: `else` runs only when the loop finished **without** `break`,
i.e. it used every step and never finished.

---

## 4. Memory

| kind | what we did |
|---|---|
| **short-term** | the `scratchpad` list — every THOUGHT/ACTION/OBSERVATION, re-sent each turn. This is the agent's working memory, and it is just a growing string. |
| **summarisation memory** | when the scratchpad passes 6 entries we spend **one** LLM call to compress the oldest into two lines of facts, and keep the last 4 verbatim. Compress, don't drop — dropping loses facts, compressing loses only wording. |
| **long-term** | not needed for a single question. Would be a vector store or `mem0`, keyed by user, surviving across tasks — retrieved by similarity, exactly like week 3 RAG but over past conversations instead of docs. |

Why summarisation exists at all: context windows are finite and cost is
per-token. Ten steps of full observations will blow past both. And week 1's
"lost in the middle" applies — a long scratchpad buries the useful part.

Verified: at step 7 the trace prints `[memory] compressed older steps`, the
run continues, and the compression call is counted in `llm_calls`
(10 steps → 12 calls). If it weren't counted, the cost comparison would lie.

---

## 5. Agent vs fixed workflow — the race

`workflow.py` solves the **same task with no LLM in the control flow**:

```
1. regex the question for ERR-####          (no LLM)
2. exact-lookup each code found             (no LLM)
3. semantic search on the question itself   (no LLM)
4. ONE LLM call to compose the answer       (1 LLM call, always)
```

That is the honest comparison. Not "agent vs nothing" — agent vs *the
sensible thing you would build if you already knew the steps*.

`race.py` scores both on 4 questions that each need **two dependent
lookups**, and reliability is **measured, not eyeballed**: each question
lists the facts the answer must contain, matched whitespace-insensitively
with week 4's `contains()`. That is week 6's ANSWER@ metric reused — after
week 6 taught us that a retrieval-only metric (hit-rate@3 = 0.889 for four
materially different strategies) can be blind to the failure you care about.

| Q | required facts | why it is multi-step |
|---|---|---|
| 1 | `refused`, `cascade` | code meaning → retry policy → cascade table |
| 2 | `180 days`, `payout` | the code lives on the refunds page, not the codes page |
| 3 | `idempotency`, `24 hours` | timeout advice → mechanism → its lifetime |
| 4 | `retry`, `jitter` | code meaning → retryable? → recommended backoff |

**Quota protection** (free tier = 20 requests/day **per model**, and a full
race is ~16): every finished question is checkpointed to
`race_results.json` immediately, a re-run **skips** finished questions
(`--fresh` to redo), and a quota `SystemExit` prints the scoreboard for what
did finish instead of losing the run. The `llm.py` disk cache means replaying
a finished question costs **0 calls**.

---

## 6. When to ship which

The decision does not depend on which one is more impressive.

**Ship the fixed workflow when you already know the steps.** It is cheaper
(1 call vs 3–5), faster, and structurally **cannot** loop — there is no loop
to run away. Nearly all of the "AI agent" work in a normal product is this.

**Ship the agent when the path genuinely depends on what it finds** — an
unknown number of lookups, or a next step only knowable after the previous
result. That flexibility is what you are paying 3–5× the calls for.

The trap: an agent on a task whose steps you already knew. You pay the
multiplier, you take on the loop risk, and you get the same answer.

---

## 7. Verified before running for real

Standing rule from week 1: **run it before handing it over.** The whole week
was dry-run with fake `llm`, `sentence_transformers` and `rank_bm25` modules
injected into `sys.modules` — real chunking, real BM25, real retrieval, zero
API calls:

| path exercised | result |
|---|---|
| full race, 4 questions, both modes | ran end-to-end, scoreboard printed, JSON saved |
| repeat guard | `repeated the same action twice - stuck` at step 2 |
| malformed reply | `model reply was malformed (no ACTION and no FINAL)` at step 1 |
| step budget | `step budget exceeded (3 steps)` |
| unknown tool name | recovered with the available-tools message |
| summarisation memory | fired at step 7, run continued, calls counted |
| checkpoint + skip | second run rebuilt the scoreboard with **0** calls |

Two things the dry run surfaced:
1. **Q4's `jitter` lives in a different chunk** ("Recommended backoff") from
   the retryable table ("Which errors to retry"). One search at k=3 can miss
   it — which is precisely where an agent's *second, refined* search should
   earn its cost. Watch this question in the real run.
2. `max_calls` is checked at the top of the loop, so the summarisation call
   can push the count one past the cap before the next check catches it.
   Known and bounded by one call; noted rather than hidden.

## Run it

```
python week7\race.py
```
