# Week 11 — Results

Production: observability, cost, and the failure → test loop.
Track E — developer documentation.

> **This file is generated.** `python week11/report.py` rewrites it from
> `logs/traces.jsonl` and `logs/*.json`. Every number below is read out of
> those files, so it cannot drift from them. Week 10 taught me that lesson
> the embarrassing way — a hand-written write-up that disagreed with its
> own data.
>
> Generated 2026-10-21T00:39:00+00:00

---

## 1. The log

`week11/logs/traces.jsonl` — one JSON line per request, one span per step.

| | |
|---|---|
| traces | **440** |
| &nbsp;&nbsp;real (this app actually ran, at least one live model call) | 19 |
| &nbsp;&nbsp;real, no live model call (every call served from the `llm.py` cache) | 13 |
| &nbsp;&nbsp;imported from week 10 | 8 |
| &nbsp;&nbsp;synthetic noise | 400 |
| window | 2026-09-05 .. 2026-10-21 |
| LLM calls | 1016 |
| served from cache | 298 (29%) |
| total cost | $0.196570 |
| cost per request | $0.000447 |
| mean latency | 8113 ms |
| p95 latency | 11216 ms |
| answers containing a removed SDK method | **3** |

The synthetic rows exist to give the log realistic **volume** — finding one
bad answer among five is reading, not searching. They are flagged
`meta.synthetic = true` in the file itself, so nobody has to take my word
for which rows are real.

A real trace whose every model call was served from the `llm.py` disk
cache is a replay of an earlier run, so it is counted on its own line
rather than as a new run. Each of its spans carries `cached = true`.

---

## 2. The support drill — vague complaint to trace id

**The complaint:** *"Someone asked your docs bot how to check webhook
signatures a while back. The code it gave us doesn't work on the new SDK."*

No trace id. No date. No username. Three filters, in this order:

```
python week11/find.py --text webhook --since 45d      narrow to the topic
python week11/find.py --deprecated                    narrow to the symptom
python week11/find.py --id tr_ace9f32c2d95      read the whole request
```

**Found: `tr_ace9f32c2d95`** (2026-10-20T15:29)

| | |
|---|---|
| question | Show me the code to verify a webhook signature from PhoenixPay. |
| removed method in the answer | **`construct_event`** |
| replacement | `Webhook.verify_and_parse` |
| documents read | 07_webhooks.md, 10_testing.md |
| corpus version | `v1` |
| steps | 3 |
| total | 70825 ms · $0.000165 |
| slowest step | #1 llm.ask (32979 ms, 47% of the request) |

**Why the answer was wrong, and why it is not the model's fault.** The
request ran against corpus `v1` — the
documentation as it stood before `11_sdk_migration.md` existed. At that
moment `construct_event` was the only documented way to do this. The answer was
correct when it was given. The documentation changed underneath it.

That is the common shape of a production "bad answer", and no amount of
prompt tuning prevents it. Only the log finds it.

---

## 3. Cost per request — measured, then improved

Fixed workload: 8 requests covering 4 distinct intents, each
asked two different ways.

| | baseline | improved | change |
|---|---|---|---|
| API calls | 8 | 4 | **−50%** |
| API calls / request | 1.00 | 0.50 | |
| total cost | $0.000489 | $0.000239 | |
| **cost per request** | **$0.000061** | **$0.000030** | **−51%** |
| input tokens | 2,965 | 1,428 | |
| output tokens | 481 | 241 | |

**The improvement:** a semantic cache in front of the model. Embed the
question, compare against questions already answered, and if the best match
clears the threshold, serve the stored answer and make no API call at all.
Cache: **4 hits / 4 misses**.

### The threshold was calibrated, not guessed

| | |
|---|---|
| chosen threshold | **0.2519** |
| same-intent pairs separate from cross-intent? | **yes** |
| weakest same-intent pair | 0.2671 |
| strongest cross-intent pair | 0.2319 |
| pairs blocked by the error-code guard first | 12 |

My first version hard-coded `0.90` because it sounded strict. Week 1
measured `ERR-4032` against `ERR-4033` at **0.970** — so 0.90 would have
served one as the other: a wrong answer, instantly, with no API call to
blame. The workload is labelled by intent, which gives ground truth for
free, so the threshold is derived from it.

There is a second, independent guard: **two questions naming different
`ERR-####` codes can never be a cache hit**, whatever the cosine says.
Similarity alone was never going to be safe for error codes.

> **What "API calls" counts here.** These are the calls each design sends
> on a **cold cache**. Cold-cache counts are the comparable number, because
> otherwise cache luck picks the winner — the same work-vs-billed discipline
> as week 10. What each recorded run actually sent live, read from its own
> trace spans:
>
> - **baseline:** 8 of 8 model calls went live, **$0.000489** live spend.
> - **improved:** spent **nothing** live — all 4 of its model calls were served from the `llm.py` cache.

**Correctness of cached answers:** 3/4 agreed with the baseline answer on error codes. A cost cut that changes answers is not a cost cut, so this is checked rather than assumed.

### What this would actually save in production — the honest number

| measured on the real log (13 requests) | |
|---|---|
| exact duplicates | 3 (25%) — **already free** via the week 1 hash cache |
| near duplicates | 1 (8%) — the only traffic this cache converts |

The −50% above is what the cache **can** do on a workload
built to contain paraphrases. **8%** is what it
would do on my actual logged traffic. Reporting only the first number would
be the dishonest version of this result, so both are here.

The log is also what makes that second number knowable at all — which is
the week's point: measure first, then cut.

---

## 4. Failure → permanent test  (replay mode)

**1/3 passing.**

| id | rule | where the failure came from | the fix | now |
|---|---|---|---|---|
| `R1` | no method removed in SDK 3.0 may appear in a code sample | week11 trace r1 | week 11 output validator (guard.validate + guard.repair) | **PASS** |
| `R2` | an ERR-4033 answer must address cascading | week10 race_results.json Q1 (single agent FAIL) | week 8 required-step gate | **FAIL** |
| `R3` | an ERR-4290 backoff answer must mention jitter | week10 race_results.json Q4 (single agent FAIL) | week 8 required-step gate | **FAIL** |

**The loop, visible in the data:**

- `R1` — first logged answer `tr_ace9f32c2d95` **failed**, latest `tr_e551b752e863` **passes**

Same assertion, same question, two different answers from two different builds. That is the whole point of keeping the old trace instead of deleting it.

Not one of these cases is invented. Each has a trace id or a results file
behind it.

**Two different guards, for two different failures** — they are easy to
confuse and they cannot substitute for each other:

| | fires | catches | cost |
|---|---|---|---|
| week 8 required-step gate | *before* the answer exists | the agent never looked something up | ~+1 call, only when it fires |
| week 11 output validator | *after* the answer exists | the answer used a removed method | $0 to check, +1 call only to repair |

The gate cannot know a method was removed. The validator cannot make the
agent read a second document. R2 and R3 need the first; R1 needs the second.

`--replay` runs all of this against answers already in the log, at **zero
API cost** — which is what makes it cheap enough to run on every change.
`--live` re-runs them for real.

---

## What I did not build, and would say so

- **No hosted tracing backend.** No LangSmith, no Phoenix, no OTel
  collector. The span shape is deliberately OTel-like, so moving to one is
  a mapping job — but I have not done it, and I would not claim I had.
- **No sampling or retention policy.** Every request is logged in full.
  At real traffic that is expensive and eventually illegal — PII in prompts
  has to expire. Fine at this scale, wrong at production scale.
- **The noise is synthetic.** It gives the log volume, not realism. Repeat
  rates measured on it are artefacts of my generator, which is why the
  cost section reports the real-traffic number separately.
- **Model routing was rejected, not tried.** The app is already pinned to
  the cheapest model in the family, so routing could only move work up in
  price. Worth revisiting if a cheaper tier appears.
- **No 10× plan beyond the obvious.** At 10× traffic the first thing to
  break is the free-tier quota, not the code — the log already shows the
  request rate that would hit it.
