"""
WEEK 8 - TRAJECTORY EVALUATION.  Zero API calls: reads week7/race_results.json.

    python week8/trajectory.py

THE IDEA IN ONE LINE
    Stop grading only the final answer. Grade the PATH the agent took.

WHY IT MATTERS
    A right answer reached by a lucky route is not a working agent - it is a
    coin that has not landed wrong yet. Change the input slightly and the same
    route returns a wrong answer, in production, to a customer.

    Week 6 taught the retrieval version of this lesson: hit-rate@3 scored 0.889
    for four materially different strategies and marked as PASS a question the
    app answered wrong. A metric can be blind. OUTCOME is that metric for
    agents - it says nothing about how the answer was reached.

THE FOUR NUMBERS THIS FILE PRODUCES
    outcome pass rate      did the final answer contain the required facts?
    trajectory pass rate   did it take an acceptable path to get there?
    tool-choice accuracy   of all tool calls made, how many were the right
                           tool with a sensible input?
    cost per task          mean and p99 LLM calls - p99 because the mean hides
                           the one run that loops and bills you.

    The GAP between the first two is the whole point of the week.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

RESULTS = os.path.join(ROOT, "week7", "race_results.json")


# ======================================================================
# 1. WHAT A CORRECT PATH LOOKS LIKE
#
# You cannot judge a trajectory without first writing down what a good one
# is. This is the agent equivalent of week 6's eval set: the answer key,
# written BEFORE looking at what the agent did.
#
# `must_call`   tools the path has to include, in order
# `why`         the reason that step is required - this is what makes the
#               expectation defensible rather than arbitrary
# ======================================================================
EXPECTED = {
    "ERR-4033": {
        "must_call": ["lookup_error_code", "search_docs"],
        "why": "the code's meaning is in the error-code table; the retry and "
               "cascade policy is in a different document, so the policy "
               "cannot be known from the code lookup alone",
    },
    "ERR-4092": {
        "must_call": ["lookup_error_code", "search_docs"],
        "why": "the code lookup gives the refund-window failure; what to do "
               "INSTEAD is a policy question that needs its own search",
    },
    "timeout": {
        "must_call": ["search_docs"],
        "why": "no error code in the question, so semantic search is the only "
               "correct entry point - calling lookup_error_code here would be "
               "a wrong-tool failure",
    },
    "ERR-4290": {
        "must_call": ["lookup_error_code", "search_docs"],
        "why": "the code lookup gives retryability; the recommended backoff "
               "lives in a separate section that the lookup does not return",
    },
}


def expectation_for(question: str) -> dict:
    """Match a question to its expected path."""
    import re
    codes = re.findall(r"ERR-\d{3,4}", question.upper())
    if codes and codes[0] in EXPECTED:
        return EXPECTED[codes[0]]
    return EXPECTED["timeout"]


# ======================================================================
# 2. THE FAILURE TAXONOMY
#
# From the brief: loops, wrong tool, made-up inputs, giving up quietly.
# Naming a failure is what lets you count it, and counting is what lets you
# prove a fix worked.
# ======================================================================
FAILURE_MODES = {
    "SKIPPED_STEP":   "answered without calling a tool the task required",
    "WRONG_TOOL":     "called a tool that cannot answer this kind of question",
    "MADE_UP_INPUT":  "passed an input that does not appear in the question",
    "LOOPED":         "repeated the same action instead of making progress",
    "GAVE_UP_QUIET":  "stopped without an answer and without an error the "
                      "caller can act on",
}


def actual_path(trace: dict) -> list:
    """The ordered list of tools the agent actually called."""
    return [s["action"] for s in trace["steps"] if s.get("action")]


def classify(trace: dict, expected: dict, question: str) -> list:
    """Return every failure mode this trajectory exhibits."""
    import re
    found = []
    path = actual_path(trace)

    # --- skipped a required step --------------------------------------
    for tool in expected["must_call"]:
        if tool not in path:
            found.append(("SKIPPED_STEP", f"never called {tool}"))

    # --- wrong tool for the question shape ----------------------------
    codes_in_q = re.findall(r"ERR-\d{3,4}", question.upper())
    if not codes_in_q and "lookup_error_code" in path:
        found.append(("WRONG_TOOL",
                      "used the error-code tool on a question with no code"))

    # --- made-up input: an ERR code that is not in the question --------
    for s in trace["steps"]:
        if s.get("action") == "lookup_error_code":
            used = re.findall(r"ERR-\d{3,4}", str(s.get("input", "")).upper())
            for c in used:
                if c not in codes_in_q:
                    found.append(("MADE_UP_INPUT",
                                  f"looked up {c}, which is not in the question"))

    # --- looped --------------------------------------------------------
    if "repeated the same action" in trace.get("stop_reason", ""):
        found.append(("LOOPED", trace["stop_reason"]))

    # --- gave up quietly -----------------------------------------------
    # An empty or malformed reply that ends the run with no answer. The
    # stop_reason IS recorded, which is what makes it debuggable at all -
    # but the caller still got nothing back.
    if trace.get("answer", "").startswith("(no answer"):
        found.append(("GAVE_UP_QUIET", trace.get("stop_reason", "no answer")))

    return found


# ======================================================================
# 3. TOOL-CHOICE ACCURACY
#
# Per CALL, not per task: of every tool call the agent made, how many were
# a tool that could plausibly help, with an input taken from the question?
# ======================================================================
def tool_call_scores(rows: list) -> tuple:
    import re
    good = total = 0
    for r in rows:
        q_codes = re.findall(r"ERR-\d{3,4}", r["q"].upper())
        for s in r["agent"]["steps"]:
            a = s.get("action")
            if not a:
                continue
            total += 1
            if a == "lookup_error_code":
                used = re.findall(r"ERR-\d{3,4}", str(s.get("input", "")).upper())
                ok = bool(q_codes) and all(c in q_codes for c in used)
            elif a == "search_docs":
                ok = True          # semantic search is never the wrong tool
            else:
                ok = False         # a tool that does not exist
            good += 1 if ok else 0
    return good, total


def percentile(values: list, p: float) -> float:
    """p99 without numpy. On 4 data points this is the max - which is the
    honest answer: with this few runs, p99 IS the worst case."""
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


# ======================================================================
# 4. THE REPORT
# ======================================================================
def main() -> None:
    if not os.path.exists(RESULTS):
        raise SystemExit(f"Missing {RESULTS}. Run week7/race.py first.")
    rows = json.load(open(RESULTS, encoding="utf-8"))

    print("=" * 78)
    print("WEEK 8 - TRAJECTORY AUDIT of the week 7 agent")
    print(f"source: week7/race_results.json   ({len(rows)} recorded runs, 0 API calls)")
    print("=" * 78)

    audit = []
    for i, r in enumerate(rows, 1):
        trace = r["agent"]
        exp = expectation_for(r["q"])
        path = actual_path(trace)
        fails = classify(trace, exp, r["q"])
        outcome_ok = trace["passed"]
        traj_ok = not fails

        audit.append({
            "n": i, "q": r["q"], "expected": exp["must_call"], "why": exp["why"],
            "actual": path, "outcome_ok": outcome_ok, "trajectory_ok": traj_ok,
            "failures": fails, "llm_calls": trace["llm_calls"],
            "seconds": trace["seconds"], "stop_reason": trace["stop_reason"],
        })

        flag = ""
        if outcome_ok and not traj_ok:
            flag = "   <<< OUTCOME-vs-TRAJECTORY GAP"
        print(f"\nQ{i}: {r['q'][:66]}...")
        print(f"   expected path : {' -> '.join(exp['must_call'])}")
        print(f"   actual path   : {' -> '.join(path) if path else '(no tool calls)'}")
        print(f"   outcome       : {'PASS' if outcome_ok else 'FAIL'}")
        print(f"   trajectory    : {'PASS' if traj_ok else 'FAIL'}{flag}")
        for mode, detail in fails:
            print(f"       {mode:<14} {detail}")
        if outcome_ok and not traj_ok:
            print(f"   why this path was required: {exp['why']}")

    # ---------------- the four numbers ----------------
    n = len(audit)
    out_pass = sum(1 for a in audit if a["outcome_ok"])
    traj_pass = sum(1 for a in audit if a["trajectory_ok"])
    good, total = tool_call_scores(rows)
    calls = [a["llm_calls"] for a in audit]

    print("\n" + "=" * 78)
    print("THE NUMBERS")
    print("=" * 78)
    print(f"  outcome pass rate     {out_pass}/{n} = {out_pass/n:.3f}")
    print(f"  trajectory pass rate  {traj_pass}/{n} = {traj_pass/n:.3f}")
    print(f"  THE GAP               {(out_pass - traj_pass)/n:+.3f}"
          f"   <- runs that look fine and are not")
    print(f"  tool-choice accuracy  {good}/{total} = "
          f"{(good/total if total else 0):.3f}")
    print(f"  cost per task         mean {sum(calls)/n:.2f} calls, "
          f"p99 {percentile(calls, 0.99):.2f} calls")

    # ---------------- failure frequency ----------------
    counts = {}
    for a in audit:
        for mode, _ in a["failures"]:
            counts[mode] = counts.get(mode, 0) + 1

    print("\n  failure modes by frequency:")
    if not counts:
        print("    (none)")
    for mode, c in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"    {c} x  {mode:<14} {FAILURE_MODES[mode]}")

    if counts:
        top = max(counts.items(), key=lambda kv: kv[1])[0]
        print(f"\n  TOP FAILURE MODE: {top}")
        print(f"    -> this is the one week 8 fixes and measures. See "
              f"week8/measure.py")

    out = os.path.join(HERE, "trajectory_audit.json")
    json.dump(audit, open(out, "w", encoding="utf-8"), indent=1)
    print(f"\nsaved: week8/trajectory_audit.json")


if __name__ == "__main__":
    main()
