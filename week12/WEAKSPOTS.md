# Known weak spots

> Write these down before somebody else finds them. A reviewer who
> discovers a limitation you did not mention stops trusting everything
> else you said.

Each item is something I **measured**, with the file that proves it.
Nothing here is a hypothetical worry.

---

## 1. A correct answer can go stale without anything changing

**The worst one, so it goes first.**

The app answers from the documents it is given. If a document is
accurate when the answer is generated and the world moves, the answer is
now wrong and nothing in the system noticed.

**Evidence:** week 11's support drill. A webhook code sample recommended
`Webhook.construct_event()` — the only documented method at the time.
SDK 3.0 removed it, and it carries security advisory PP-2025-004. The
answer was *correct when it was given*.

**What I did:** an output validator that rejects any answer containing a
removed method and repairs it against the migration notes
(`week11/guard.py`), plus a permanent regression test (`R1` in
`week11/regress.py`).

**What is still open:** the validator only knows the symbols I listed in
`week11/corpus.py`. A method deprecated tomorrow is invisible until
somebody adds it. **The right fix is to generate that list from the SDK
changelog rather than maintain it by hand, and I have not built that.**

The detector also matches only the **call** form — `construct_event(` —
so that prose warning about a removed method is allowed. (The first
version matched the bare name, which made the guard reject its own
repair.) The cost: a bare reference with no parentheses, such as
`handler = Webhook.construct_event`, is not caught. None of the real
answers in the log contains one in code, so I have no measured frequency
for it.

**The guard can still reject its own repair.** The call-form match cannot
tell a call in a code block from a name in a sentence, and the migration
notes themselves write the removed method with parentheses. So warning
prose that copies that style matches exactly like a real call:

```
**Important:** The old `Webhook.construct_event()` method has been removed   -> flagged
- Replace `Webhook.construct_event()` with `Webhook.verify_and_parse()`.     -> flagged
```

Measured in two traces:

| trace | what happened |
|---|---|
| `tr_cad83e8715f8` | R1. The agent's first answer was already correct; the bare-name detector of the time rejected it, and `repair()` rewrote it as the first line above — which the current detector still flags |
| `tr_46d76933bff3` | the SDK 3.0 upgrade answer: correct migration advice, flagged for all three removed methods |

R1's current pass, `tr_411184667fa4`, needed no repair and happened to
name the method without parentheses.

---

## 2. Dense retrieval cannot distinguish error codes

`ERR-4032` ("insufficient funds — retrying may work") and `ERR-4033`
("issuer refused — retrying will not work") embed at **0.970** cosine
similarity. They mean opposite things. Meaning-based search cannot
separate them.

**Evidence:** week 1 measurement; week 4 found `ERR-4092`'s chunk ranked
**28th of 47** under dense search.

**What I did:** a second index. `lookup_error_code` uses BM25 exact
keyword matching and discards any chunk that does not literally contain
the code.

**What is still open:** the split is only as good as the agent's choice
of tool. Which is weak spot 3.

---

## 3. The agent skips a lookup and answers anyway

The top failure mode across the whole project, and it keeps reappearing
in new costumes.

The agent looks up the error code, gets a confident-looking chunk, and
answers **without** searching the policy — which lives in a different
document.

**Evidence:**

| where | what happened |
|---|---|
| week 8 trajectory audit | `SKIPPED_STEP` was the top failure, 3 of 4 runs. Outcome-vs-trajectory gap **+0.250** — one run was right *by luck*, on a path that skipped a required step |
| week 10 live race | reproduced on **2 of 4** questions: Q1 missing `cascade`, Q4 missing `jitter` |

**What I did:** the required-step gate (week 8). It rejects a FINAL that
skipped a required tool, says what was skipped, and lets the agent carry
on — bounded at 2 pushes so the gate cannot itself cause a loop. Measured
effect: trajectory pass rate **0.250 → 1.000**, `SKIPPED_STEP` **3 → 0**,
at a cost of **+6 LLM calls** across four questions.

**What is still open:** the required tools are derived from a regex on the
question (`ERR-\d{3,4}` means "look the code up *and* search the policy").
That generalises to unseen questions, but it is a rule I wrote, not a
learned one. A question needing two documents with no error code in it
gets only `search_docs` required.

---

## 4. Everything is measured on 10 documents

47 chunks. Roughly 15,000 words. Every retrieval number in this
repository — recall, rank, reranker gain — is measured at that scale.

**Why it matters:** retrieval gets harder as the corpus grows, not
linearly. At 10,000 documents the dense index needs a real vector store,
BM25 needs tuning, and the "28th of 47" style of failure becomes "28th of
40,000" — which is invisible rather than merely bad.

**Nothing here has been tested at realistic scale, and I would not claim
any of these numbers hold there.**

---

## 5. The free tier is the binding constraint on everything

20 requests per day, **per model**.

That single number shaped the engineering more than any technical choice:
the disk cache in `llm.py`, per-question checkpointing in every race
script, deliberately scheduling zero-API work, and splitting work across
two models to split the quota.

**Evidence:** week 10's race hit the cap mid-run and had to resume from a
checkpoint the next day.

**What it means for the results:** small sample sizes everywhere. Week
10's verdict rests on four questions, one run each. That is a real signal.
It is not a statistic, and there are no variance estimates anywhere in
this project.

---

## 6. The cost improvement is smaller than its headline

Week 11's semantic cache cuts API calls roughly in half **on a workload
built to contain paraphrases**.

On my actual logged traffic the near-duplicate rate is far lower — and
most of the repeats are byte-identical, which the hash cache in `llm.py`
has handled for free since week 1.

`week11/RESULTS.md` reports **both** numbers for exactly this reason.
Quoting only the workload figure would be the dishonest version of that
result.

**What is still open:** my log is too small to claim a production repeat
rate at all.

---

## 7. A semantic cache can serve a confidently wrong answer

The failure mode is nasty: no error, no slow response, no API call to
blame. Just the wrong answer, instantly.

Given weak spot 2 — `ERR-4032` vs `ERR-4033` at 0.970 — a similarity
threshold alone was never going to be safe.

**What I did:** two independent guards. The threshold is *calibrated*
from labelled same-intent/cross-intent pairs rather than guessed, and a
hard rule blocks any cache hit between questions naming different
`ERR-####` codes, whatever the similarity says.

**What is still open:** the hard rule covers error codes because that is
where I measured the danger. Two questions about *different payment
methods* could still collide, and I have not tested that.

---

## 8. Multi-agent is slower than it looks worth

Week 10's squad answered better — **4/4 vs 2/4** — but cost **2.44×** the
calls and **4.57×** the wall-clock.

83 seconds for four questions is a product problem, not a rounding error.
And its entire advantage came from one thing: forcing a second lookup.
Week 8's gate buys that same second lookup for about **+1 call per
question** instead of +13 total.

**So I did not ship the squad.** The recommendation is the single agent
*with* the gate — which is what `app.py` runs.

**What would change my mind:** running the specialists in parallel. That
would not cut tokens, but it would close most of the latency gap. Untested
here, so not claimed.

---

## 9. Operational gaps, stated plainly

- **No authentication, no rate limiting, no multi-user.** It is a CLI.
- **No log rotation or retention policy.** Every request is logged in
  full, forever. Prompts contain user text, so at real volume that becomes
  a legal problem before it becomes a disk problem.
- **MCP:** week 9 built **tools** only, over **stdio**. The *resources*
  and *prompts* primitives are not built, and there is no remote MCP or
  auth.
- **The noise in the request log is synthetic.** It gives the log
  realistic volume, not realistic content. It is flagged
  `meta.synthetic = true` in the file so nobody has to take my word for
  which rows are real.
- **No CI.** The regression suite runs when somebody types the command.

---

## What I would fix first, in order

1. **Generate the deprecated-symbol list from the SDK changelog.** Weak
   spot 1 is the only one that ships *vulnerable code* to a developer, and
   its fix currently depends on me remembering to update a dict.
2. **Test retrieval at 1,000+ documents.** Every number in this repo has
   an unknown lifespan until this is done.
3. **Log rotation and retention.** Cheap to add, and it only gets harder
   to retrofit.
4. **Run the week 10 race more than once per question.** Turn a signal
   into a statistic.
