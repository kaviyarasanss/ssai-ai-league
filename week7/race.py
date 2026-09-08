"""
WEEK 7 - THE RACE. Agent vs fixed workflow on speed, cost and reliability.

    python week7/race.py            run both on 4 multi-step questions
    python week7/race.py --quiet    numbers only

RELIABILITY is measured, not eyeballed: each question lists the facts the
answer MUST contain (same technique as week 6's ANSWER@3 - a documented
string, matched whitespace-insensitively). A question passes only if every
required fact is present.

Every question needs at least TWO lookups that depend on each other, so it is
a genuine multi-step task rather than one search dressed up.
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from week4.evalset import contains
from week7.agent import run_agent
from week7.workflow import run_workflow
from week7.tools import init
from llm import MODEL, print_stats

QUIET = "--quiet" in sys.argv
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "race_results.json")

# The free tier is 20 requests/day/model. A full race is ~16. So:
#   - every finished question is written to disk immediately
#   - a re-run SKIPS finished questions (--fresh to ignore the checkpoint)
#   - hitting the wall prints the scoreboard for what DID finish
# The llm.py disk cache also means replaying a finished question is free.
FRESH = "--fresh" in sys.argv


def _load_done() -> dict:
    if FRESH or not os.path.exists(OUT):
        return {}
    try:
        return {r["q"]: r for r in json.load(open(OUT, encoding="utf-8"))}
    except Exception:
        return {}

# Each needs a code lookup AND a separate policy lookup - two dependent steps.
QUESTIONS = [
    {
        "q": "A payment failed with ERR-4033. Should I retry the same card, "
             "and will it cascade to another acquirer?",
        "must": ["refused", "cascade"],
        "why_multistep": "code meaning -> retry policy -> cascade table",
    },
    {
        "q": "I got ERR-4092 when issuing a refund. What happened, and what "
             "should I do instead?",
        "must": ["180 days", "payout"],
        "why_multistep": "code lives on the refunds page, not the codes page",
    },
    {
        "q": "A payment request timed out. What should I send on the retry so "
             "the customer is not charged twice, and how long is it valid for?",
        "must": ["idempotency", "24 hours"],
        "why_multistep": "timeout advice -> idempotency mechanism -> its lifetime",
    },
    {
        "q": "ERR-4290 keeps happening. Is it retryable, and what backoff "
             "should I use?",
        "must": ["retry", "jitter"],
        "why_multistep": "code meaning -> retryable? -> recommended backoff",
    },
]


def score(answer: str, must: list[str]) -> tuple[bool, list[str]]:
    missing = [m for m in must if not contains(answer, m)]
    return (not missing), missing


def main() -> None:
    n = init()
    print(f"Index ready: {n} chunks · model {MODEL}\n")

    done = _load_done()
    rows = []
    for i, item in enumerate(QUESTIONS, 1):
        if item["q"] in done:
            print(f"Q{i}: already in race_results.json - skipping "
                  f"(--fresh to redo)")
            rows.append(done[item["q"]])
            continue
        print("=" * 76)
        print(f"Q{i}: {item['q']}")
        print(f"    (multi-step because: {item['why_multistep']})")
        print("=" * 76)

        print("\n--- AGENT ---")
        a = run_agent(item["q"], verbose=not QUIET)
        a_ok, a_missing = score(a["answer"], item["must"])

        print("\n--- FIXED WORKFLOW ---")
        w = run_workflow(item["q"], verbose=not QUIET)
        w_ok, w_missing = score(w["answer"], item["must"])

        print(f"\n  required facts : {item['must']}")
        print(f"  agent          : {'PASS' if a_ok else 'FAIL'}"
              f"{'' if a_ok else '  missing ' + str(a_missing)}"
              f"   {a['llm_calls']} calls  {a['seconds']}s  "
              f"{a['n_steps']} steps  [{a['stop_reason']}]")
        print(f"  workflow       : {'PASS' if w_ok else 'FAIL'}"
              f"{'' if w_ok else '  missing ' + str(w_missing)}"
              f"   {w['llm_calls']} calls  {w['seconds']}s  "
              f"{w['n_steps']} steps")
        print()

        rows.append({"q": item["q"], "must": item["must"],
                     "agent": {**a, "passed": a_ok, "missing": a_missing},
                     "workflow": {**w, "passed": w_ok, "missing": w_missing}})
        # checkpoint after EVERY question, so a quota wall costs us nothing
        _save(rows)

    # ---------------- the scoreboard ----------------
    def tot(mode, key):
        return sum(r[mode][key] for r in rows)

    n_q = len(rows)
    a_pass = sum(1 for r in rows if r["agent"]["passed"])
    w_pass = sum(1 for r in rows if r["workflow"]["passed"])

    print("=" * 76)
    print("THE RACE")
    print("=" * 76)
    print(f"{'':<16}{'AGENT':>14}{'WORKFLOW':>14}")
    print(f"{'reliability':<16}{f'{a_pass}/{n_q}':>14}{f'{w_pass}/{n_q}':>14}")
    print(f"{'LLM calls':<16}{tot('agent','llm_calls'):>14}{tot('workflow','llm_calls'):>14}")
    print(f"{'total seconds':<16}{round(tot('agent','seconds'),1):>14}"
          f"{round(tot('workflow','seconds'),1):>14}")
    print(f"{'total steps':<16}{tot('agent','n_steps'):>14}{tot('workflow','n_steps'):>14}")
    print()
    ac, wc = tot("agent", "llm_calls"), tot("workflow", "llm_calls")
    if wc:
        print(f"  cost ratio     : the agent used {ac/wc:.1f}x the LLM calls")
    print(f"  stop reasons   : "
          f"{ {r['agent']['stop_reason'] for r in rows} }")

    _save(rows)
    print("\nsaved: week7/race_results.json")
    print_stats()


def _save(rows) -> None:
    json.dump(rows, open(OUT, "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        # llm.py raises SystemExit with a clean message when quota is gone.
        print(f"\nSTOPPED: {e}")
        print("Partial results are in week7/race_results.json. Re-run "
              "`python week7/race.py` tomorrow - finished questions are "
              "skipped and cached calls are free.")
        raise
