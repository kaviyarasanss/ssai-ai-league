"""
WEEK 8 - FIX THE TOP FAILURE AND MEASURE IT.

    python week8/measure.py           before/after on all 4 questions
    python week8/measure.py --quiet   numbers only

WHAT IS BEING FIXED
    The trajectory audit (week8/trajectory.py) ranked the failure modes by
    frequency. Top of the list: SKIPPED_STEP - the agent answered without
    calling a tool the task required. Three of four runs did it, and one of
    those three (Q2, ERR-4092) still produced the RIGHT ANSWER. That is the
    outcome-vs-trajectory gap: a lucky path.

THE FIX
    A required-step gate in the agent loop. Before a FINAL is accepted, check
    that the tools this task requires were actually called. If not, reject the
    answer, tell the agent what it skipped, and let it continue. Bounded by
    max_gate_pushes so the gate cannot itself cause a loop.

WHY THE COMPARISON IS FAIR
    Both runs use the SAME agent code, the same model, the same tools, the
    same index, the same questions, in the same process. The only difference
    is whether require_tools is passed. One variable.

    Week 6 taught this the hard way: applying a guard to one side of a
    comparison silently made it two changes, and the resulting number looked
    fine and meant nothing. An unfair comparison does not announce itself.

COST
    The llm.py disk cache means the two configs share every prompt up to the
    point the gate fires, so the "after" run only pays for the steps that
    actually differ.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from week7.agent import run_agent                       # noqa: E402
from week7.race import QUESTIONS                        # noqa: E402
from week7.tools import init                            # noqa: E402
from week4.evalset import contains                      # noqa: E402
from week8.trajectory import (expectation_for, classify,  # noqa: E402
                              actual_path, FAILURE_MODES)
from llm import MODEL, print_stats                      # noqa: E402

QUIET = "--quiet" in sys.argv
OUT = os.path.join(HERE, "measure_results.json")


def required_tools(question: str) -> list:
    """What this task requires. Derived from the question, not hard-coded per
    question - so it generalises to a question the agent has never seen.

    An ERR-#### in the question means the code must be looked up exactly AND
    the surrounding policy searched. No code means semantic search only.
    """
    if re.search(r"ERR-\d{3,4}", question.upper()):
        return ["lookup_error_code", "search_docs"]
    return ["search_docs"]


def score(trace: dict, item: dict) -> dict:
    """Grade one run on BOTH axes: outcome and trajectory."""
    missing_facts = [m for m in item["must"] if not contains(trace["answer"], m)]
    exp = expectation_for(item["q"])
    failures = classify(trace, exp, item["q"])
    return {
        "outcome_ok": not missing_facts,
        "missing_facts": missing_facts,
        "trajectory_ok": not failures,
        "failures": failures,
        "path": actual_path(trace),
        "llm_calls": trace["llm_calls"],
        "seconds": trace["seconds"],
        "stop_reason": trace["stop_reason"],
        "gate_pushes": trace.get("gate_pushes", 0),
    }


def run_config(label: str, *, gated: bool) -> list:
    print("\n" + "=" * 78)
    print(f"{label}")
    print("=" * 78)
    rows = []
    for i, item in enumerate(QUESTIONS, 1):
        req = required_tools(item["q"]) if gated else None
        if not QUIET:
            print(f"\nQ{i}: {item['q'][:64]}...")
            if req:
                print(f"    required: {' + '.join(req)}")
        trace = run_agent(item["q"], require_tools=req, verbose=not QUIET)
        s = score(trace, item)
        rows.append({"q": item["q"], **s})
        print(f"    outcome {'PASS' if s['outcome_ok'] else 'FAIL'}"
              f"   trajectory {'PASS' if s['trajectory_ok'] else 'FAIL'}"
              f"   path: {' -> '.join(s['path']) or '(none)'}"
              f"   {s['llm_calls']} calls"
              + (f"   gate fired {s['gate_pushes']}x" if s["gate_pushes"] else ""))
    return rows


def rates(rows: list) -> dict:
    n = len(rows)
    o = sum(1 for r in rows if r["outcome_ok"])
    t = sum(1 for r in rows if r["trajectory_ok"])
    counts = {}
    for r in rows:
        for mode, _ in r["failures"]:
            counts[mode] = counts.get(mode, 0) + 1
    return {"n": n, "outcome": o / n, "trajectory": t / n, "gap": (o - t) / n,
            "calls": sum(r["llm_calls"] for r in rows),
            "seconds": round(sum(r["seconds"] for r in rows), 1),
            "modes": counts}


def main() -> None:
    n = init()
    print(f"Index ready: {n} chunks · model {MODEL}")
    print("Fixing the top failure from the trajectory audit: SKIPPED_STEP")

    before = run_config("BEFORE - week 7 agent, no required-step gate", gated=False)
    after = run_config("AFTER  - same agent + required-step gate", gated=True)

    b, a = rates(before), rates(after)

    print("\n" + "=" * 78)
    print("BEFORE / AFTER")
    print("=" * 78)
    print(f"{'':<24}{'BEFORE':>10}{'AFTER':>10}{'DELTA':>10}")
    for key, name in (("trajectory", "trajectory pass rate"),
                      ("outcome", "outcome pass rate"),
                      ("gap", "outcome-trajectory gap")):
        print(f"{name:<24}{b[key]:>10.3f}{a[key]:>10.3f}{a[key]-b[key]:>+10.3f}")
    print(f"{'total LLM calls':<24}{b['calls']:>10}{a['calls']:>10}"
          f"{a['calls']-b['calls']:>+10}")
    print(f"{'total seconds':<24}{b['seconds']:>10}{a['seconds']:>10}"
          f"{a['seconds']-b['seconds']:>+10.1f}")

    print("\n  failure modes:")
    for mode in sorted(set(b["modes"]) | set(a["modes"])):
        bc, ac = b["modes"].get(mode, 0), a["modes"].get(mode, 0)
        print(f"    {mode:<14} {bc} -> {ac}   ({ac-bc:+d})  {FAILURE_MODES[mode]}")

    print(f"""
  READ THIS THE RIGHT WAY
    The headline is the TRAJECTORY rate, not the outcome rate. The outcome
    rate can stay flat while the fix works perfectly - a lucky right answer
    was already counted as a pass, so forcing the correct path does not add
    a point. What it removes is the luck.

    The cost column is the honest other half: the gate spends extra LLM calls
    to buy a correct path. If trajectory went up and calls went up, that is
    the trade being made, and it should be stated as a trade rather than a
    free win.""")

    json.dump({"before": before, "after": after,
               "rates": {"before": b, "after": a}},
              open(OUT, "w", encoding="utf-8"), indent=1)
    print(f"\nsaved: week8/measure_results.json")
    print_stats()


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        print(f"\nSTOPPED: {e}")
        print("Quota gone. Re-run tomorrow - cached prompts replay free.")
        raise
