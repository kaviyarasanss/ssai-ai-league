"""
WEEK 11 - GENERATE RESULTS.md FROM THE LOGS.

WHY THIS FILE EXISTS - and it is a week 10 scar
    In week 10 I hand-wrote RESULTS.md from one question's output, then
    re-ran the race and forgot to update it. For a while the repository
    contained a write-up that disagreed with its own data file, and an
    earlier version contained STUB numbers presented as measurements.
    Nobody caught it but me, and only because I went looking.

    The fix is structural, not a promise to be more careful:

        RESULTS.md is GENERATED. Every number in it is read out of
        logs/*.json at generation time. It cannot drift, because there is
        no hand-written copy of the numbers to drift from.

    If an experiment has not been run, the section says so instead of
    carrying an old number forward. A missing number is honest. A stale
    number is not.

RUN
    python week11/report.py
"""
import io
import sys
import json
import pathlib
import datetime

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from week11 import obs, corpus                                   # noqa: E402

LOGS = HERE / "logs"
OUT = HERE / "RESULTS.md"
MISSING = "_not run yet — run the command above and regenerate this file._"


def _j(name: str):
    p = LOGS / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def section_log(rows: list[dict]) -> str:
    if not rows:
        return f"## 1. The log\n\n{MISSING}\n"
    real = [r for r in rows if not r["meta"].get("synthetic")]
    syn = len(rows) - len(real)
    imported = [r for r in real if r["meta"].get("imported_from")]
    ran = [r for r in real if not r["meta"].get("imported_from")]
    # A trace whose every model call came from the llm.py disk cache is a
    # REPLAY of an earlier run, not a new one. Counting it as a real run
    # would inflate the one number this file exists to keep honest.
    replayed = [r for r in ran
                if all(s["cached"] for s in r["spans"] if s["name"] == "llm.ask")]
    usd = sum(r["totals"]["usd"] for r in rows)
    ms = sorted(r["totals"]["ms"] for r in rows)
    calls = sum(r["totals"]["llm_calls"] for r in rows)
    hits = sum(r["totals"]["cache_hits"] for r in rows)
    bad = [r for r in rows if corpus.find_deprecated(r.get("answer") or "")]
    p95 = ms[max(0, int(len(ms) * 0.95) - 1)]

    return f"""## 1. The log

`week11/logs/traces.jsonl` — one JSON line per request, one span per step.

| | |
|---|---|
| traces | **{len(rows)}** |
| &nbsp;&nbsp;real (this app actually ran, at least one live model call) | {len(ran) - len(replayed)} |
| &nbsp;&nbsp;real, no live model call (every call served from the `llm.py` cache) | {len(replayed)} |
| &nbsp;&nbsp;imported from week 10 | {len(imported)} |
| &nbsp;&nbsp;synthetic noise | {syn} |
| window | {min(r['ts'] for r in rows)[:10]} .. {max(r['ts'] for r in rows)[:10]} |
| LLM calls | {calls} |
| served from cache | {hits} ({hits / max(calls, 1) * 100:.0f}%) |
| total cost | ${usd:.6f} |
| cost per request | ${usd / len(rows):.6f} |
| mean latency | {sum(ms) / len(ms):.0f} ms |
| p95 latency | {p95:.0f} ms |
| answers containing a removed SDK method | **{len(bad)}** |

The synthetic rows exist to give the log realistic **volume** — finding one
bad answer among five is reading, not searching. They are flagged
`meta.synthetic = true` in the file itself, so nobody has to take my word
for which rows are real.

A real trace whose every model call was served from the `llm.py` disk
cache is a replay of an earlier run, so it is counted on its own line
rather than as a new run. Each of its spans carries `cached = true`.
"""


def section_drill(rows: list[dict]) -> str:
    bad = [r for r in rows
           if corpus.find_deprecated(r.get("answer") or "")
           and not r["meta"].get("synthetic")]
    if not bad:
        return ("## 2. The support drill\n\nNo answer in the log contains a "
                "removed SDK method — nothing to find.\n")
    first = sorted(bad, key=lambda r: r["ts"])[0]
    syms = corpus.find_deprecated(first["answer"])
    spans = first["spans"]
    docs = sorted({d for s in spans for d in (s.get("doc_ids") or [])})
    slow = max(spans, key=lambda s: s["ms"]) if spans else None

    return f"""## 2. The support drill — vague complaint to trace id

**The complaint:** *"Someone asked your docs bot how to check webhook
signatures a while back. The code it gave us doesn't work on the new SDK."*

No trace id. No date. No username. Three filters, in this order:

```
python week11/find.py --text webhook --since 45d      narrow to the topic
python week11/find.py --deprecated                    narrow to the symptom
python week11/find.py --id {first['trace_id']}      read the whole request
```

**Found: `{first['trace_id']}`** ({first['ts'][:16]})

| | |
|---|---|
| question | {' '.join(first['question'].split())[:90]} |
| removed method in the answer | **`{'`, `'.join(syms)}`** |
| replacement | `{'`, `'.join(corpus.DEPRECATED[s] for s in syms)}` |
| documents read | {', '.join(docs) or '—'} |
| corpus version | `{first['meta'].get('corpus', '?')}` |
| steps | {len(spans)} |
| total | {first['totals']['ms']:.0f} ms · ${first['totals']['usd']:.6f} |
{f"| slowest step | #{slow['i']} {slow['name']} ({slow['ms']:.0f} ms, {slow['ms'] / max(first['totals']['ms'], 1) * 100:.0f}% of the request) |" if slow else ""}

**Why the answer was wrong, and why it is not the model's fault.** The
request ran against corpus `{first['meta'].get('corpus', '?')}` — the
documentation as it stood before `11_sdk_migration.md` existed. At that
moment `{syms[0]}` was the only documented way to do this. The answer was
correct when it was given. The documentation changed underneath it.

That is the common shape of a production "bad answer", and no amount of
prompt tuning prevents it. Only the log finds it.
"""


def section_cost(d) -> str:
    if not d or not d.get("baseline") or not d.get("improved"):
        return ("## 3. Cost per request\n\n```\npython week11/cost.py --all\n"
                f"```\n\n{MISSING}\n")
    b, i, cal, j = d["baseline"], d["improved"], d.get("calibration"), \
        d.get("justification")
    c = i.get("cache", {})
    chk = d.get("correctness") or {}

    drop_calls = (1 - i["api_calls"] / max(b["api_calls"], 1)) * 100
    drop_cost = (1 - i["usd_per_request"] /
                 max(b["usd_per_request"], 1e-12)) * 100

    out = f"""## 3. Cost per request — measured, then improved

Fixed workload: {b['requests']} requests covering 4 distinct intents, each
asked two different ways.

| | baseline | improved | change |
|---|---|---|---|
| API calls | {b['api_calls']} | {i['api_calls']} | **−{drop_calls:.0f}%** |
| API calls / request | {b['api_calls_per_request']:.2f} | {i['api_calls_per_request']:.2f} | |
| total cost | ${b['usd_total']:.6f} | ${i['usd_total']:.6f} | |
| **cost per request** | **${b['usd_per_request']:.6f}** | **${i['usd_per_request']:.6f}** | **−{drop_cost:.0f}%** |
| input tokens | {b['tok_in']:,} | {i['tok_in']:,} | |
| output tokens | {b['tok_out']:,} | {i['tok_out']:,} | |

**The improvement:** a semantic cache in front of the model. Embed the
question, compare against questions already answered, and if the best match
clears the threshold, serve the stored answer and make no API call at all.
Cache: **{c.get('hits', 0)} hits / {c.get('misses', 0)} misses**.
"""
    if cal:
        out += f"""
### The threshold was calibrated, not guessed

| | |
|---|---|
| chosen threshold | **{cal['threshold']}** |
| same-intent pairs separate from cross-intent? | **{'yes' if cal['separable'] else 'NO'}** |
| weakest same-intent pair | {cal['min_same']} |
| strongest cross-intent pair | {cal['max_diff']} |
| pairs blocked by the error-code guard first | {cal['n_blocked_by_guard']} |

My first version hard-coded `0.90` because it sounded strict. Week 1
measured `ERR-4032` against `ERR-4033` at **0.970** — so 0.90 would have
served one as the other: a wrong answer, instantly, with no API call to
blame. The workload is labelled by intent, which gives ground truth for
free, so the threshold is derived from it.

There is a second, independent guard: **two questions naming different
`ERR-####` codes can never be a cache hit**, whatever the cosine says.
Similarity alone was never going to be safe for error codes.
"""
    if chk:
        out += (f"\n**Correctness of cached answers:** "
                f"{chk.get('passed', 0)}/{chk.get('checked', 0)} agreed with "
                f"the baseline answer on error codes. A cost cut that changes "
                f"answers is not a cost cut, so this is checked rather than "
                f"assumed.\n")
    if j and j.get("real"):
        r = j["real"]
        out += f"""
### What this would actually save in production — the honest number

| measured on the real log ({r['n']} requests) | |
|---|---|
| exact duplicates | {r['exact']} ({r['exact_rate'] * 100:.0f}%) — **already free** via the week 1 hash cache |
| near duplicates | {r['near']} ({r['near_rate'] * 100:.0f}%) — the only traffic this cache converts |

The −{drop_calls:.0f}% above is what the cache **can** do on a workload
built to contain paraphrases. **{r['near_rate'] * 100:.0f}%** is what it
would do on my actual logged traffic. Reporting only the first number would
be the dishonest version of this result, so both are here.

The log is also what makes that second number knowable at all — which is
the week's point: measure first, then cut.
"""
    return out


def section_regress(d) -> str:
    if not d:
        return ("## 4. Failure → test\n\n```\npython week11/regress.py\n"
                f"```\n\n{MISSING}\n")
    res = d["results"]
    done = [r for r in res if r["status"] != "NO DATA"]
    passed = sum(1 for r in done if r["status"] == "PASS")

    rows = "\n".join(
        f"| `{r['id']}` | {r['rule']} | {r['origin']} | {r.get('fix', '—')} | "
        f"**{r['status']}** |" for r in res)

    flip = [r for r in res if r.get("first_passed") is False
            and r.get("last_passed") is True]
    flip_txt = ""
    if flip:
        flip_txt = "\n".join(
            f"- `{r['id']}` — first logged answer `{r['first_trace']}` "
            f"**failed**, latest `{r['last_trace']}` **passes**" for r in flip)
        flip_txt = (f"\n**The loop, visible in the data:**\n\n{flip_txt}\n\n"
                    f"Same assertion, same question, two different answers "
                    f"from two different builds. That is the whole point of "
                    f"keeping the old trace instead of deleting it.\n")

    return f"""## 4. Failure → permanent test  ({d['mode']} mode)

**{passed}/{len(done)} passing.**

| id | rule | where the failure came from | the fix | now |
|---|---|---|---|---|
{rows}
{flip_txt}
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
"""


def main() -> None:
    rows = obs.load()
    cost = _j("cost_results.json")
    regress = _j("regress_results.json")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds")

    body = f"""# Week 11 — Results

Production: observability, cost, and the failure → test loop.
Track E — developer documentation.

> **This file is generated.** `python week11/report.py` rewrites it from
> `logs/traces.jsonl` and `logs/*.json`. Every number below is read out of
> those files, so it cannot drift from them. Week 10 taught me that lesson
> the embarrassing way — a hand-written write-up that disagreed with its
> own data.
>
> Generated {now}

---

{section_log(rows)}
---

{section_drill(rows)}
---

{section_cost(cost)}
---

{section_regress(regress)}
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
"""
    OUT.write_text(body, encoding="utf-8")
    print(f"wrote {OUT}  ({len(body)} chars)")
    for name, d in (("cost_results.json", cost),
                    ("regress_results.json", regress)):
        print(f"  {name}: {'found' if d else 'MISSING - section left blank'}")


if __name__ == "__main__":
    main()
