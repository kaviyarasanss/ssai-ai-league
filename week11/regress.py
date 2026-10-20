"""
WEEK 11 - THE FAILURE-TO-TEST LOOP. Every real failure becomes a test.

THE IDEA
    A bug you fixed once and did not test is a bug you will ship again.
    So the loop is:

        production failure  ->  find it in the log  ->  write the assertion
        ->  fix  ->  the assertion runs forever

    The important detail: the test cases are not invented. Each one below
    is a failure I actually MEASURED and have a trace_id or a results file
    for. Test suites made of imagined failures test your imagination.

THE THREE CASES, AND WHERE EACH CAME FROM
    R1  deprecated method in a code sample
        source: week 11 trace r1 (logs/traces.jsonl)
        The agent handed a developer `Webhook.construct_event()`, which SDK
        3.0 removes and which carries advisory PP-2025-004.

    R2  cascade fact missing
        source: week 10 race_results.json, Q1, single agent
        Answered ERR-4033 from the error-code doc and never looked up the
        cascade policy in 06_routing_cascading.md.

    R3  jitter fact missing
        source: week 10 race_results.json, Q4, single agent
        Said ERR-4290 was retryable with backoff, never mentioned jitter,
        which is in 05_retries_idempotency.md.

    R2 and R3 are the SAME failure as R1 in a different costume: the fact
    that changes the answer lives in a document the question does not point
    at. Three traces, one root cause - which is exactly the kind of thing a
    test suite is supposed to make visible.

TWO MODES
    --replay   (default)  0 API calls. Runs the assertions against answers
                          already in the log. This is the production
                          pattern: replay yesterday's traffic against
                          today's build.
    --live                Re-runs each case through the guarded path. Costs
                          roughly 2-4 API calls per case.

    Replay is the one that runs in CI. Live is the one you run when you
    change the fix.

RUN
    python week11/regress.py             replay, free
    python week11/regress.py --live      re-run for real
"""
import io
import sys
import json
import pathlib
import argparse

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from week11 import obs, guard, corpus                            # naqa: E402

OUT = HERE / "logs" / "regress_results.json"

# ----------------------------------------------------------------------
# THE CASES
#
# `must_not_contain` and `must_contain` are deliberately crude string
# checks. A fancier assertion would be more precise and less trustworthy -
# I want a mentor to be able to read the rule and agree with it in one
# second, and I want it to keep working when the wording of answers drifts.
# ----------------------------------------------------------------------
CASES = [
    {
        "id": "R1",
        "origin": "week11 trace r1",
        "question": "Show me the code to verify a webhook signature from "
                    "PhoenixPay.",
        "rule": "no method removed in SDK 3.0 may appear in a code sample",
        "no_deprecated_calls": True,
        "must_not_contain": [],
        "must_contain": [],
        "fix": "week 11 output validator (guard.validate + guard.repair)",
        "require_tools": ["search_docs"],
    },
    {
        "id": "R2",
        "origin": "week10 race_results.json Q1 (single agent FAIL)",
        "question": "A payment failed with ERR-4033. Should I retry the same "
                    "card, and will it cascade to another acquirer?",
        "rule": "an ERR-4033 answer must address cascading",
        "must_not_contain": [],
        "must_contain": ["cascade"],
        "fix": "week 8 required-step gate",
        "require_tools": ["lookup_error_code", "search_docs"],
    },
    {
        "id": "R3",
        "origin": "week10 race_results.json Q4 (single agent FAIL)",
        "question": "ERR-4290 keeps happening. Is it retryable, and what "
                    "backoff should I use?",
        "rule": "an ERR-4290 backoff answer must mention jitter",
        "must_not_contain": [],
        "must_contain": ["jitter"],
        "fix": "week 8 required-step gate",
        "require_tools": ["lookup_error_code", "search_docs"],
    },
]


def assert_answer(case: dict, answer: str) -> dict:
    """Grade one answer.

    TWO BUGS FOUND BY RUNNING THIS LIVE, AND WHAT THEY TAUGHT ME
      1. This function used to do its own substring check for deprecated
         symbols, while guard.validate() used corpus.find_deprecated().
         When I fixed the detector to match a CALL rather than a mention,
         I fixed it in one place only - so the guard passed an answer and
         the test failed the same answer. Live run R1: `repaired=False`
         next to `forbidden: ['construct_event']`.
         TWO DETECTORS FOR ONE RULE WILL ALWAYS DRIFT. There is now one,
         and both the guard and this test call it.
      2. An EMPTY answer used to be reported as `required_missing:
         ['cascade']`, which reads as "the agent answered badly" when the
         truth was "the agent produced nothing at all". Those need
         completely different fixes, so they now report differently.
    """
    text = answer or ""

    if not text.strip():
        return {"passed": False, "forbidden_present": [],
                "required_missing": [], "empty_answer": True}

    low = text.lower()
    bad = []
    if case.get("no_deprecated_calls"):
        # the SAME detector the guard uses - one rule, one implementation
        bad += corpus.find_deprecated(text)
    bad += [s for s in case.get("must_not_contain", []) if s.lower() in low]
    missing = [s for s in case["must_contain"] if s.lower() not in low]
    return {"passed": not bad and not missing,
            "forbidden_present": bad, "required_missing": missing,
            "empty_answer": False}


# ----------------------------------------------------------------------
def replay() -> list[dict]:
    """Run the assertions against what is already logged. Zero API calls."""
    rows = obs.load()
    results = []

    for case in CASES:
        # Match the most recent logged answer for this question. Falls back
        # to a loose match so a reworded question still finds its trace.
        key = case["question"][:40].lower()
        hits = [r for r in rows
                if key in (r.get("question") or "").lower() and r.get("answer")]
        hits.sort(key=lambda r: r["ts"])

        if not hits:
            results.append({**_meta(case), "status": "NO DATA",
                            "note": "no logged answer for this question yet"})
            continue

        # Report the FIRST and the LAST logged answer. The first is usually
        # the failure that created the test; the last is the current state.
        first, last = hits[0], hits[-1]
        r_first = assert_answer(case, first["answer"])
        r_last = assert_answer(case, last["answer"])

        results.append({
            **_meta(case),
            "status": "PASS" if r_last["passed"] else "FAIL",
            "first_trace": first["trace_id"],
            "first_passed": r_first["passed"],
            "last_trace": last["trace_id"],
            "last_passed": r_last["passed"],
            "forbidden_present": r_last["forbidden_present"],
            "required_missing": r_last["required_missing"],
            "n_logged": len(hits),
        })
    return results


def live() -> list[dict]:
    """Re-run each case through the guarded path. Costs API calls."""
    corpus.use("v2")
    results = []
    for case in CASES:
        print(f"\n--- {case['id']}  {case['question'][:58]}...")
        with obs.trace(case["question"], track="E",
                       experiment="regress-live", case=case["id"],
                       synthetic=False) as t:
            g = guard.answer_with_guard(
                case["question"], require_tools=case.get("require_tools"))
            t.answer = g["answer"]
            t.stop_reason = "completed"
        chk = assert_answer(case, g["answer"])
        print(f"    {'PASS' if chk['passed'] else 'FAIL'}  "
              f"trace={t.id}  repaired={g['repaired']}")
        if not chk["passed"]:
            if chk.get("empty_answer"):
                print("      EMPTY ANSWER - the agent produced nothing. "
                      "This is the week 7 empty-reply failure, not a "
                      "content failure.")
            else:
                print(f"      forbidden: {chk['forbidden_present']}  "
                      f"missing: {chk['required_missing']}")
        results.append({**_meta(case), "status": "PASS" if chk["passed"] else "FAIL",
                        "last_trace": t.id, "repaired": g["repaired"],
                        **chk})
    return results


def _meta(case: dict) -> dict:
    return {"id": case["id"], "origin": case["origin"], "rule": case["rule"],
            "question": case["question"], "fix": case.get("fix", "")}


# ----------------------------------------------------------------------
def report(results: list[dict], mode: str) -> int:
    print("\n" + "=" * 74)
    print(f"REGRESSION SUITE ({mode})  -  every case is a failure that "
          f"really happened")
    print("=" * 74)
    passed = 0
    for r in results:
        mark = {"PASS": "PASS", "FAIL": "FAIL", "NO DATA": "SKIP"}[r["status"]]
        print(f"\n[{mark}] {r['id']}  {r['rule']}")
        print(f"       origin: {r['origin']}")
        if r.get("fix"):
            print(f"       fix:    {r['fix']}")
        if r["status"] == "NO DATA":
            print(f"       {r['note']}")
            continue
        if r.get("first_trace"):
            fp = "passed" if r.get("first_passed") else "FAILED"
            lp = "passed" if r.get("last_passed") else "FAILED"
            print(f"       first logged answer {r['first_trace']}  -> {fp}")
            print(f"       latest logged answer {r['last_trace']} -> {lp}")
            if not r.get("first_passed") and r.get("last_passed"):
                print(f"       ^ this is the loop working: the failure that "
                      f"created the test is now caught and fixed")
        if r["status"] == "FAIL":
            if r.get("empty_answer"):
                print("       EMPTY ANSWER - no output at all (week 7 "
                      "empty-reply failure, not a content failure)")
            if r.get("forbidden_present"):
                print(f"       forbidden present: {r['forbidden_present']}")
            if r.get("required_missing"):
                print(f"       required missing:  {r['required_missing']}")
        passed += r["status"] == "PASS"

    total = sum(1 for r in results if r["status"] != "NO DATA")
    print("\n" + "-" * 74)
    print(f"{passed}/{total} passing"
          + (f"   ({len(results)-total} skipped - no logged data)"
             if total != len(results) else ""))
    print("-" * 74)
    OUT.write_text(json.dumps({"mode": mode, "results": results}, indent=1),
                   encoding="utf-8")
    print(f"saved -> {OUT}")
    return 0 if passed == total and total else 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    if args.live:
        sys.exit(report(live(), "live"))
    sys.exit(report(replay(), "replay"))


if __name__ == "__main__":
    main()
