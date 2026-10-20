"""
WEEK 11 - RUN THE AGENT WITH LOGGING ON, and build a log worth searching.

WHAT THIS PRODUCES
    week11/logs/traces.jsonl  - one JSON line per request

    Two kinds of line, and the difference is recorded in the line itself so
    nobody has to take my word for it:

      meta.synthetic = false   REAL requests. The week 7 agent actually ran,
                               actually called the model, actually cost money.
      meta.synthetic = true    NOISE. Generated offline, zero API calls, to
                               give the log realistic VOLUME.

    The noise exists because "find one bad answer among thousands" is not a
    drill if the log has five lines in it. Searching five lines is reading.
    Searching 400 is a procedure - and the procedure is the deliverable.

THE PLANTED BAD ANSWER
    One real request is deliberately run against corpus v1 - the 10-document
    corpus as it stood BEFORE 11_sdk_migration.md was published.

    That is not cheating, and it is not a fake answer. It is a faithful
    reconstruction of what production returned last month: at that time
    `Webhook.construct_event()` was the only documented way to verify a
    signature, so the agent cited it, correctly, from the docs it had.

    Today that method is removed in SDK 3.0 and carries a security
    advisory. The answer did not change. The world did.

    That is the realistic version of "a customer says it gave a bad answer"
    — far more common than the model hallucinating.

API BUDGET
    The free tier is 20 requests/day PER MODEL. The real runs below cost
    roughly 2 calls each. Every finished request is checkpointed, so a 429
    half way through costs you the rest of the run, not the start of it.

RUN
    python week11/run_logged.py            real requests + 400 noise lines
    python week11/run_logged.py --noise-only    noise only, zero API calls
    python week11/run_logged.py --fresh    wipe the log first
"""
import io
import sys
import json
import time
import random
import pathlib
import argparse
import datetime

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from week11 import obs, corpus                                   # noqa: E402

DONE = HERE / "logs" / "_done.json"

# ----------------------------------------------------------------------
# THE REAL REQUESTS
#
# `corpus` is the version of the documentation the request runs against.
# Only the first one uses v1, and that is the planted bad answer.
# ----------------------------------------------------------------------
REAL = [
    {
        "id": "r1",
        "corpus": "v1",
        "q": "Show me the code to verify a webhook signature from PhoenixPay.",
    },
    {
        "id": "r2",
        "corpus": "v2",
        "q": "How do I register a webhook endpoint, and what happens if my "
             "endpoint is slow to respond?",
    },
    {
        "id": "r3",
        "corpus": "v2",
        "q": "I got ERR-4092 when issuing a refund. What happened and what "
             "should I do?",
    },
    {
        "id": "r4",
        "corpus": "v2",
        "q": "A payment request timed out. What should I send on the retry?",
    },
    {
        "id": "r5",
        "corpus": "v2",
        "q": "What do I need to change to upgrade to PhoenixPay SDK 3.0?",
    },
]

# ----------------------------------------------------------------------
# NOISE - plausible Track E developer-documentation traffic.
#
# Generated from templates, not from the model. Zero API calls. Spread over
# the last 45 days so date filtering is a real filter and not a no-op.
# ----------------------------------------------------------------------
NOISE_Q = [
    "How do I install the PhoenixPay SDK?",
    "What Python version does the SDK need?",
    "Why is my amount showing as $1499 instead of $14.99?",
    "What does a sk_test_ key do?",
    "How long do test payments stay in the dashboard?",
    "What is an idempotency key for?",
    "Which errors should I retry?",
    "What is the difference between ERR-4032 and ERR-4033?",
    "How do I handle a 429 from the API?",
    "What is the rate limit on the payments endpoint?",
    "How do I list payments for one customer?",
    "What statuses can a payment move through?",
    "Can a refund be partial?",
    "How long does a refund take to settle?",
    "What is cascading and when does it trigger?",
    "How do I pick which acquirer to route to?",
    "Are webhook events delivered in order?",
    "How many times is a failed webhook retried?",
    "What happens after the final webhook retry?",
    "How do I test a declined card?",
    "Which test card triggers 3-D Secure?",
    "What does ERR-5030 mean?",
    "Is the SDK thread safe?",
    "How do I set a custom timeout?",
    "Where do I find my API keys?",
    "How do I rotate a webhook secret?",
    "What is the maximum description length?",
    "Does the SDK support async?",
    "How do I add metadata to a payment?",
    "What currencies are supported?",
]
NOISE_ANSWERS = [
    "See the quickstart: `pip install phoenixpay`, then set "
    "`phoenixpay.api_key`. Requires Python 3.9+.",
    "Amounts are in the smallest currency unit, so 1499 means $14.99.",
    "Retry only errors where waiting could change the outcome: ERR-4290 "
    "with backoff, and ERR-5000/5030/5040 with an idempotency key.",
    "Failed webhook deliveries retry for 24 hours, then the event is marked "
    "`undelivered`.",
    "Events are not guaranteed to arrive in order; always re-read the "
    "payment before acting on an event.",
    "Store `event.id` and ignore duplicates - delivery is at-least-once.",
]
NOISE_TOOLS = ["search_docs", "lookup_error_code"]
NOISE_DOCS = ["01_quickstart.md", "02_authentication.md",
              "03_payment_lifecycle.md", "04_error_codes.md",
              "05_retries_idempotency.md", "06_routing_cascading.md",
              "07_webhooks.md", "08_refunds.md", "09_rate_limits.md",
              "10_testing.md"]


# ----------------------------------------------------------------------
# IMPORTING HISTORY - the data flywheel, applied backwards.
#
# Week 10 produced two REAL measured failures (Q1 missing `cascade`, Q4
# missing `jitter`) and they are sitting in week10/race_results.json. They
# are production failures in every sense that matters: a real model, real
# retrieval, a real wrong answer.
#
# Leaving them in a results file means they can only ever be read by a
# human. Importing them into the log means the regression suite can assert
# against them automatically, forever. Costs nothing - the runs already
# happened.
# ----------------------------------------------------------------------
def import_week10() -> int:
    src = ROOT / "week10" / "race_results.json"
    if not src.exists():
        print("  week10/race_results.json not found - skipping import")
        return 0

    rows = json.loads(src.read_text(encoding="utf-8"))
    existing = {r["meta"].get("imported_from")
                for r in obs.load() if r["meta"].get("imported_from")}
    n = 0

    for i, r in enumerate(rows):
        for mode in ("single", "squad"):
            run = r.get(mode) or {}
            if not run.get("answer"):
                continue
            tag = f"week10:Q{i+1}:{mode}"
            if tag in existing:
                continue

            t = obs.Trace(r["q"], track="E", synthetic=False,
                          imported_from=tag, source="week10 race",
                          corpus="v1", mode=mode,
                          week10_passed=run.get("passed"),
                          week10_missing=run.get("missing"))
            # Reconstruct spans from what week 10 actually recorded. Only
            # the fields week 10 measured are filled in; the rest stay 0
            # rather than being invented.
            for s in run.get("steps", []):
                if s.get("action"):
                    t.add_span(f"tool.{s['action']}", 0.0, 0, 0, False,
                               note="imported from week10",
                               tool_input=s.get("input", ""))
            calls = run.get("llm_calls", 0) or 1
            tok_in = (run.get("work_tokens", 0) or 0)
            for c in range(calls):
                t.add_span("llm.ask",
                           (run.get("seconds", 0) * 1000.0) / calls,
                           tok_in // calls, 0, False,
                           note="imported from week10 (tokens are the run "
                                "total split evenly)",
                           model="models/gemini-3.5-flash-lite")
            t.answer = run["answer"]
            t.stop_reason = run.get("stop_reason", "completed")
            t.ts = "2026-10-07T12:00:00+00:00"      # when week 10 ran
            t.backdate()
            t.write()
            n += 1
    return n


def _load_done() -> set:
    if DONE.exists():
        try:
            return set(json.loads(DONE.read_text()))
        except Exception:
            return set()
    return set()


def _save_done(done: set) -> None:
    DONE.write_text(json.dumps(sorted(done)))


# ----------------------------------------------------------------------
def write_noise(n: int, seed: int = 11) -> int:
    """Append n synthetic traces. No model, no network, no cost."""
    rng = random.Random(seed)
    now = datetime.datetime.now(datetime.timezone.utc)
    written = 0

    for _ in range(n):
        q = rng.choice(NOISE_Q)
        t = obs.Trace(q, track="E", synthetic=True, source="noise-generator")
        # Backdate: spread over 45 days, business-ish hours.
        when = now - datetime.timedelta(
            days=rng.randint(0, 45), hours=rng.randint(0, 10),
            minutes=rng.randint(0, 59))
        t.ts = when.isoformat(timespec="seconds")

        n_tools = rng.choice([1, 1, 1, 2])
        for _i in range(n_tools):
            tool = rng.choice(NOISE_TOOLS)
            t.add_span(f"tool.{tool}", rng.uniform(40, 900), 0, 0, False,
                       note="synthetic",
                       tool_input=q[:40],
                       doc_ids=rng.sample(NOISE_DOCS, k=rng.randint(1, 3)))
            t.add_span("llm.ask", rng.uniform(600, 4200),
                       rng.randint(700, 1600), rng.randint(60, 420),
                       rng.random() < 0.25, note="synthetic",
                       model="models/gemini-3.5-flash-lite")
        t.add_span("llm.ask", rng.uniform(600, 3000),
                   rng.randint(700, 1500), rng.randint(80, 400),
                   rng.random() < 0.25, note="synthetic",
                   model="models/gemini-3.5-flash-lite")

        t.answer = rng.choice(NOISE_ANSWERS)
        t.stop_reason = "completed"
        t.backdate()          # total ms must equal the spans, not 0
        t.write()
        written += 1
    return written


# ----------------------------------------------------------------------
def run_real(only: set | None = None) -> list[str]:
    """Run the real requests through the instrumented week 7 agent."""
    from week7.agent import run_agent

    done = _load_done()
    ids = []
    current_corpus = None

    for item in REAL:
        if item["id"] in done:
            print(f"  [skip] {item['id']} already logged")
            continue
        if only and item["id"] not in only:
            continue

        # Switching corpus version means re-embedding, so do it only when
        # the version actually changes.
        if item["corpus"] != current_corpus:
            n = corpus.use(item["corpus"])
            current_corpus = item["corpus"]
            print(f"\n  [corpus {item['corpus']}] {n} chunks indexed")

        print(f"\n--- {item['id']}  ({item['corpus']})  {item['q'][:60]}...")
        with obs.trace(item["q"], track="E",
                       request_id=item["id"],
                       corpus=item["corpus"],
                       synthetic=False,
                       client="docs-assistant/1.4") as t:
            try:
                res = run_agent(item["q"], verbose=False)
                t.answer = res.get("answer")
                t.stop_reason = res.get("stop_reason")
            except SystemExit as e:
                # llm.py raises SystemExit on an exhausted quota. Catch it so
                # the trace is still written - an unlogged failure is the
                # worst possible outcome for an observability week.
                t.stop_reason = "quota exhausted"
                t.error = str(e)
                print(f"  !! {e}")
                ids.append(t.id)
                _save_done(done)
                return ids

        tot = t.totals()
        flagged = corpus.find_deprecated(t.answer or "")
        print(f"    trace_id={t.id}  {tot['ms']:.0f}ms  "
              f"{tot['llm_calls']} llm  {tot['tool_calls']} tool  "
              f"${tot['usd']:.6f}")
        if flagged:
            print(f"    ** answer contains deprecated symbol(s): "
                  f"{', '.join(flagged)}")
        done.add(item["id"])
        _save_done(done)
        ids.append(t.id)

    return ids


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--noise", type=int, default=400)
    ap.add_argument("--noise-only", action="store_true")
    ap.add_argument("--real-only", action="store_true")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--no-import", action="store_true",
                    help="skip importing week 10's measured failures")
    args = ap.parse_args()

    if args.fresh:
        for p in (obs.TRACES, DONE):
            if p.exists():
                p.unlink()
        print("log wiped")

    if not args.no_import:
        n = import_week10()
        print(f"imported {n} historical traces from week 10 (0 API calls)")

    if not args.real_only:
        n = write_noise(args.noise)
        print(f"wrote {n} synthetic traces (0 API calls)")

    if not args.noise_only:
        ids = run_real()
        print(f"\nreal traces written: {len(ids)}")

    rows = obs.load()
    real = [r for r in rows if not r["meta"].get("synthetic")]
    print(f"\nlog now holds {len(rows)} traces "
          f"({len(real)} real, {len(rows) - len(real)} synthetic)")
    print(f"  {obs.TRACES}")


if __name__ == "__main__":
    main()
