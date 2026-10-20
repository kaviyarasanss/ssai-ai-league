# Week 11 — Production: observability, cost, and the failure → test loop

Track E — developer documentation.
Measured numbers live in `RESULTS.md` (generated). This file is the ideas.

---

## 1. The one idea

In production nobody is watching. So the app has to watch itself:

| | means | file |
|---|---|---|
| **observable** | you can see what it did, afterwards | `obs.py`, `find.py` |
| **affordable** | you know what it costs, and can cut it | `cost.py` |
| **self-improving** | every real failure becomes a permanent test | `regress.py`, `guard.py` |

> **If it isn't logged, it didn't happen.** Not a slogan — a description of
> your actual position when a customer complains. Without a log your only
> honest answer is "I can't check."

---

## 2. Traces and spans

Two words, and they are the whole model:

```
trace  = one user request, start to finish      -> one JSON line
span   = one step inside it                     -> one entry in that line
```

```
trace tr_9f21ab40c7d3   "verify a webhook signature"      1,243 ms   $0.000133
 ├─ span 1  llm.ask            412 ms   328 in /  22 out   $0.000042
 ├─ span 2  tool.search_docs   235 ms                      $0
 │          docs: 01_quickstart.md, 02_authentication.md, 07_webhooks.md
 └─ span 3  llm.ask            596 ms   625 in /  73 out   $0.000092
```

**Why per-step and not one total.** A total tells you a request was slow.
A span tells you *which step* was slow — and only the second one can be
acted on. "1,243 ms" is a complaint; "span 3, the second model call, 596 ms,
48% of the request" is a task.

Same for money. One total hides the fact that nearly all the cost is in the
model calls and none of it in retrieval — which immediately tells you that
caching the model call is worth more than speeding up the search.

### What goes in a span

| field | why |
|---|---|
| `name` | what happened — `llm.ask`, `tool.search_docs` |
| `ms` | find the slow step |
| `tok_in` / `tok_out` | find the big step |
| `usd` | find the expensive step |
| `cached` | a 0-cost step is not a free step |
| `doc_ids` | **the single most useful field** — a wrong answer is nearly always a retrieval story |

### LangSmith / Phoenix / OpenTelemetry

These are the hosted versions of exactly this. OpenTelemetry is the open
standard for trace/span data; LangSmith and Phoenix are LLM-specific
products built around it.

I wrote mine by hand for two reasons, and I will say both out loud:
writing it is the only way to understand what those tools record, and
nothing here needs a network service. The span shape is deliberately
OTel-ish — `trace_id`, span name, duration, attributes — so swapping in a
real backend later is a mapping job, not a rewrite.

**What I give up:** a UI, distributed tracing across services, sampling,
retention policies, and alerting. All real, none needed at this scale.

---

## 3. The support drill

The runbook is `DRILL.md`; one completed run is `RESULTS.md` §2.

The point in one line: **turn the complaint into filters before you read
anything.** "Something about webhooks a few weeks back, the code doesn't
work any more" is three flags — `--text webhook --since 45d --deprecated` —
and three flags beat twenty minutes of scrolling.

The deeper lesson from the drill I ran: **the answer was correct when it
was given.** The method it recommended was the documented one at the time;
the SDK deprecated it afterwards. No prompt tuning prevents that failure.
Only a log finds it, and only a validator stops it recurring.

---

## 4. Cost

**You cannot cut a cost you have not measured.** So the order is fixed:

1. **measure** cost per request, live
2. **justify** — prove from the log that the fix will actually fire
3. **improve**, then measure again

Step 2 is the one people skip. `cost.py --justify` reads the real log and
measures how much traffic is actually repeat traffic. If that number were
low, the honest conclusion would be "a semantic cache is the wrong fix" —
and I would have reported that instead.

### The levers, and why I picked the one I picked

| lever | verdict |
|---|---|
| **model routing** (LiteLLM) | **rejected** — already pinned to the cheapest model in the family. Routing could only move work *up* in price. |
| **shorter retrieval** | **rejected** — week 8 showed my failures are *skipped* lookups, not oversized ones. Trimming context would worsen a known failure to save a few hundred tokens. |
| **prompt / exact-hash cache** | **already there** since week 1, and already counted in the baseline. Only fires on byte-identical prompts. |
| **semantic cache** | **chosen** — two people asking the same thing in different words is the shape the exact cache misses entirely. |

### How a semantic cache works, and how it bites

Embed the question. Compare to questions already answered. Above a
threshold, serve the stored answer and make **no API call at all**.

The danger is a **false hit** — two questions that look similar and need
different answers. Week 1 measured `ERR-4032` against `ERR-4033` at
**0.970**. A cache that returns the wrong answer is not a saving, it is an
outage that is harder to debug than a crash.

Two defences, and the second is the one that matters:

1. **a calibrated threshold** — derived from labelled same-intent vs
   cross-intent pairs, not guessed. My first version hard-coded 0.90
   because it *sounded* strict; 0.970 walks straight through it.
2. **a hard guard** — two questions naming different `ERR-####` codes can
   never be a cache hit, whatever the cosine says. Similarity alone was
   never going to be safe for error codes.

### The honesty problem in this number

A cache measured on a workload *built* to contain paraphrases will look
brilliant. The same cache on real traffic may do almost nothing.
`RESULTS.md` §3 reports **both**: the fixed-workload saving and the
near-duplicate rate in the actual log. Quoting only the first would be the
dishonest version of this result.

It also separates **exact** duplicates from **near** duplicates, because
exact ones were already free via the week 1 hash cache. A new cache must
not take credit for savings that already existed.

---

## 5. The failure → test loop (the data flywheel)

```
production failure -> find it in the log -> write the assertion
   -> watch it FAIL -> fix -> it is guarded forever
```

"Watch it fail" is not a formality. **A regression test that was never seen
to fail is not evidence of anything** — it may be asserting something that
was always true.

My three cases are all failures that really happened:

| case | origin | failure |
|---|---|---|
| R1 | week 11 trace `r1` | handed a developer a removed SDK method in a code sample |
| R2 | week 10 `race_results.json` Q1 | ERR-4033 answer never mentioned cascading |
| R3 | week 10 `race_results.json` Q4 | ERR-4290 backoff answer never mentioned jitter |

R2 and R3 were sitting in a results file where only a human could read
them. Importing them into the log turned two dead measurements into two
live assertions, for free — the runs had already happened.

**R1, R2 and R3 are the same root cause in different costumes:** the fact
that changes the answer lives in a document the question does not point at.
Week 8 found it, week 10 watched it reproduce live, week 11 guards it.

### Two guards, two different jobs

| | fires | catches | cost |
|---|---|---|---|
| **week 8 required-step gate** | *before* the answer exists | the agent never looked something up | ~+1 call, only when it fires |
| **week 11 output validator** | *after* the answer exists | the answer used a removed method | $0 to check, +1 call only to repair |

Neither can do the other's job. The gate cannot know a method was removed;
the validator cannot make the agent read a second document.

**Why validate rather than just fix retrieval.** Publishing the migration
doc makes the right answer *findable*, not *found* — the query says
"webhook signature", and the document that best matches those words is
still the old page. Retrieval tuning is a probability; validation is a
guarantee. For something that ships vulnerable code to a developer, I want
the guarantee.

**Note what `repair()` does not do:** blind string replacement. The
replacement method is not a rename — different argument, different security
behaviour — so substituting the name would produce code that does not run.

---

## 6. The 10× plan

What breaks first, in order, measured from the log rather than guessed:

1. **the free-tier quota (20 req/day/model).** Already the binding
   constraint today. At 10× it is the only thing that matters.
2. **cost**, which is why the cache exists — but see the honest number.
3. **the log file.** JSONL append is fine at thousands; at millions it
   needs rotation, sampling, and a retention policy. Prompts contain user
   text, so "keep everything forever" eventually becomes a legal problem,
   not a disk problem.
4. **p95 latency**, not mean. The mean hides the slow tail, and the tail is
   what users describe as "it hung".

**Fine-tuning is the last resort,** not the first. It is slower to iterate,
harder to roll back, and it cannot fix a stale *document* — which is the
failure I actually measured this week. Retrieval and validation both beat
it here.

---

## 7. Likely evaluator questions

**What is a trace and what is a span?** A trace is one request end to end;
a span is one step inside it. One line of JSON per trace, one entry per
span.

**Why log per step instead of per request?** A total tells you a request
was slow. A span tells you which step was slow. Only the second is
actionable.

**How would you find a bad answer from a vague complaint?** Turn the
complaint into filters — topic, time window, symptom — then open the single
trace. `DRILL.md`, and §2 of `RESULTS.md` is a completed run.

**How do you know your cost fix helped?** I measured cost per request
before and after on the same fixed workload. And I measured, from the real
log, how often the fix would actually fire — both numbers are in the
write-up.

**Why not model routing?** Already on the cheapest model in the family;
routing could only move work up in price.

**What is the risk of a semantic cache?** Serving a stored answer to a
question that only *looks* similar. ERR-4032 vs ERR-4033 embed at 0.970.
Hence a calibrated threshold plus a hard error-code guard.

**What is the failure-to-test loop?** Every real production failure becomes
a permanent test case, so the same mistake cannot quietly return.

**Did you watch your tests fail first?** Yes — replay shows the first
logged answer failing and the latest passing for the imported week 10 cases.

**Why is RESULTS.md generated?** Because in week 10 I hand-wrote one and it
drifted from its own data file. Generating it makes drift impossible rather
than unlikely.

---

## Run it

```
python week11/run_logged.py            real requests + week 10 import + noise
python week11/find.py --stats          log health
python week11/find.py --deprecated     the bad answers
python week11/cost.py --all            justify, calibrate, measure, improve
python week11/regress.py               the suite, replayed, 0 API calls
python week11/regress.py --live        the suite, re-run for real
python week11/report.py                regenerate RESULTS.md
```
