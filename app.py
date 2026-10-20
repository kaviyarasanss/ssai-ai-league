#!/usr/bin/env python
"""
PhoenixPay SDK Docs Answer Engine
=================================
WEEK 12 CAPSTONE - the single entry point. Everything, behind one command.

    python app.py --check                 does this machine work?
    python app.py "how do I verify a webhook signature?"
    python app.py --repl                  ask repeatedly
    python app.py --eval                  the full test suite
    python app.py --demo                  the four-part demo

WHAT THIS FILE ACTUALLY IS
    Eleven weeks produced eleven folders. That is a portfolio, not an app.
    This file is the seam: ONE request path that uses all of it, so there
    is exactly one thing to run, one thing to explain, and one thing that
    can break.

THE REQUEST PATH - every week shows up here, in order
    week 3   chunk the docs, embed them, keep the matrix in memory
    week 4   BM25 index alongside, because dense search cannot tell
             ERR-4032 from ERR-4033 (they embed at 0.970)
    week 11  corpus v2 - the 10 docs plus the SDK 3.0 migration note
    week 7   the ReAct agent: THOUGHT / ACTION / OBSERVATION, with four
             stop conditions so it cannot run away
    week 8   the required-step gate - refuse a FINAL that skipped a lookup
    week 11  the output validator - refuse an answer using a removed method
    week 11  a trace written for every request, one span per step
    week 10  the meter - tokens counted two ways, cost per request

    Weeks 1, 2, 5, 6, 9 are in here too, as decisions rather than code:
    the token/cost model, the structured-output discipline, the failure
    taxonomy that produced the gate, the eval suite --eval runs, and the
    MCP work that proved tools can be swapped without touching the agent.

THE TWO SWITCHES THAT MATTER
    --no-gate and --no-guard turn off week 8's gate and week 11's
    validator. They exist for one reason: a demo where nothing ever fails
    is a demo that is hiding something. These let me show the real failure
    first, then switch the fix on and show the same question working.
"""
import io
import os
import re
import sys
import json
import time
import pathlib
import argparse
import subprocess

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

BANNER = "PhoenixPay SDK Docs Answer Engine"
SEP = "=" * 72


# ======================================================================
# PREFLIGHT - run this first, on any machine
#
# This exists because of the fresh-eyes test. Every failure a stranger
# can hit on a new machine shows up here with the exact command to fix
# it, instead of as a stack trace four layers deep in somebody else's
# code. Checked in dependency order: no point testing the index if numpy
# is missing.
# ======================================================================
def check(verbose: bool = True) -> bool:
    ok = True

    def line(label, good, detail=""):
        nonlocal ok
        ok = ok and good
        if verbose:
            print(f"  [{'OK ' if good else 'FAIL'}] {label:<34} {detail}")

    print(f"\n{SEP}\n{BANNER} - preflight\n{SEP}")

    v = sys.version_info
    line("python >= 3.10", v >= (3, 10), f"found {v.major}.{v.minor}.{v.micro}")

    for mod, pip in [("numpy", "numpy"),
                     ("dotenv", "python-dotenv"),
                     ("google.genai", "google-genai"),
                     ("sentence_transformers", "sentence-transformers"),
                     ("rank_bm25", "rank-bm25")]:
        try:
            __import__(mod)
            line(f"package {pip}", True)
        except Exception as e:
            line(f"package {pip}", False,
                 f"-> pip install -r requirements.txt   ({type(e).__name__})")

    env = HERE / ".env"
    line(".env exists", env.exists(),
         "" if env.exists() else "-> copy .env.example to .env and paste your key")
    if env.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except Exception:
            pass
        key = os.environ.get("GEMINI_API_KEY", "")
        line("GEMINI_API_KEY set", bool(key),
             f"...{key[-4:]}" if key else "-> add it to .env")

    docs = HERE / "week3" / "docs"
    n_docs = len(list(docs.glob("*.md"))) if docs.exists() else 0
    line("documentation corpus", n_docs >= 10, f"{n_docs} markdown files")

    if not ok:
        print(f"\n{SEP}\nNOT READY - fix the FAIL lines above, then re-run.\n{SEP}")
        return False

    # Only now is it worth paying for the slow part.
    print("\n  building the index (first run downloads the embedding model,")
    print("  roughly 90 MB - after that it is cached and takes a few seconds)")
    try:
        t0 = time.time()
        from week11 import corpus
        n = corpus.use("v2")
        line("index built", True,
             f"{n} chunks from {n_docs + 1} docs in {time.time() - t0:.1f}s")
    except Exception as e:
        line("index built", False, f"{type(e).__name__}: {e}")
        return False

    print(f"\n{SEP}")
    print("READY.  Try:  python app.py \"what does ERR-4092 mean?\"")
    print(SEP)
    return True


# ======================================================================
# THE REQUEST PATH
# ======================================================================
def required_tools(question: str) -> list:
    """What this question requires before an answer is acceptable.

    DERIVED from the question, never hard-coded per question - that is
    what makes it work on a question the agent has never seen. An
    ERR-#### means look the code up exactly AND search the surrounding
    policy, because week 8 measured that the policy almost always lives
    in a different document from the code table.
    """
    if re.search(r"ERR-\d{3,4}", question.upper()):
        return ["lookup_error_code", "search_docs"]
    return ["search_docs"]


def answer(question: str, use_gate: bool = True, use_guard: bool = True,
           verbose: bool = True) -> dict:
    """One question, all the way through. Always writes a trace."""
    from week11 import obs, corpus, guard
    from week7.agent import run_agent

    corpus.use("v2")
    req = required_tools(question) if use_gate else None

    if verbose:
        print(f"\n{SEP}\nQ: {question}\n{SEP}")
        print(f"  gate:  {'ON  requires ' + ', '.join(req) if req else 'OFF'}")
        print(f"  guard: {'ON' if use_guard else 'OFF'}")

    t0 = time.time()
    with obs.trace(question, track="E", entry="app.py",
                   gate=use_gate, guard=use_guard, synthetic=False) as t:
        res = run_agent(question, verbose=False, require_tools=req)
        text = res.get("answer") or ""
        violations = guard.validate(text) if use_guard else []
        repaired = False

        if violations:
            if verbose:
                print(f"\n  [guard] REJECTED - {guard.explain(violations)}")
                print(f"  [guard] repairing with the migration document...")
            text = guard.repair(question, text, violations)
            repaired = True

        t.answer = text
        t.stop_reason = res.get("stop_reason")
        totals = t.totals()

    tools_used = [s["name"][5:] for s in t.spans if s["name"].startswith("tool.")]
    still_bad = guard.validate(text)

    if verbose:
        print(f"\n{text}\n")
        print("-" * 72)
        print(f"  trace_id   {t.id}")
        print(f"  tools      {', '.join(tools_used) or 'none'}")
        print(f"  gated      {len(res.get('gated') or [])} time(s)"
              f"{'  <- the agent tried to answer early' if res.get('gated') else ''}")
        print(f"  repaired   {repaired}")
        print(f"  steps      {totals['spans']}  "
              f"({totals['llm_calls']} model, {totals['tool_calls']} tool)")
        print(f"  time       {time.time() - t0:.2f}s")
        print(f"  cost       ${totals['usd']:.6f}")
        if still_bad:
            print(f"  ** WARNING: answer still contains "
                  f"{guard.explain(still_bad)}")
        print(f"\n  inspect:   python week11/find.py --id {t.id}")
        print("-" * 72)

    return {"answer": text, "trace_id": t.id, "tools": tools_used,
            "gated": res.get("gated") or [], "repaired": repaired,
            "clean": not still_bad, "totals": totals,
            "seconds": round(time.time() - t0, 2)}


def repl() -> None:
    print(f"\n{SEP}\n{BANNER}\n{SEP}")
    print("Ask a question. Blank line or Ctrl-C to quit.\n")
    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not q:
            return
        try:
            answer(q)
        except SystemExit as e:
            print(f"\n  stopped: {e}")
            return
        except Exception as e:
            # A REPL that dies on one bad question is a bad REPL.
            print(f"\n  error: {type(e).__name__}: {e}")


# ======================================================================
# THE FULL SUITE
#
# Subprocesses, not imports, for a deliberate reason: this is exactly
# what a stranger would type. If a step only works when imported from
# here, it is broken for them and I want to find that out.
# ======================================================================
SUITE = [
    ("week 8  trajectory audit", [sys.executable, "week8/trajectory.py"], 0),
    ("week 11 regression suite", [sys.executable, "week11/regress.py"], 0),
    ("week 11 cost report", [sys.executable, "week11/cost.py", "--report"], 0),
]


def run_suite() -> int:
    print(f"\n{SEP}\n{BANNER} - full suite\n{SEP}")
    print("Only zero-API steps run here. The ones that cost quota are listed")
    print("at the end so nothing silently spends your daily allowance.\n")

    failures = 0
    for label, cmd, _ in SUITE:
        print(f"\n{'-' * 72}\n>>> {label}\n    $ {' '.join(cmd)}\n{'-' * 72}")
        try:
            p = subprocess.run(cmd, cwd=HERE, timeout=900)
            if p.returncode != 0:
                failures += 1
                print(f"    ^ exit code {p.returncode}")
        except FileNotFoundError:
            failures += 1
            print(f"    SKIPPED - {cmd[1]} not found")
        except subprocess.TimeoutExpired:
            failures += 1
            print("    TIMED OUT")

    print(f"\n{SEP}")
    print(f"suite finished - {failures} step(s) reported a problem")
    print("\ncosts quota, run deliberately:")
    print("  python week11/run_logged.py     populate the log   (~10 requests)")
    print("  python week11/cost.py --all     cost before/after  (~8 requests)")
    print("  python week11/regress.py --live re-run for real    (~8 requests)")
    print("  python week10/race.py           squad vs single    (~20 requests)")
    print(SEP)
    return failures


# ======================================================================
# THE FOUR-PART DEMO
#
# The brief asks for: a real run, a real failure, a number that improved,
# and what is next. Part 2 is the one that matters - a demo where nothing
# fails is a demo that is hiding something, so this one breaks the app on
# purpose, with the fix switched off, and then switches it back on.
# ======================================================================
DEMO_Q = "A payment failed with ERR-4033. Should I retry the same card, " \
         "and will it cascade to another acquirer?"


def demo(live: bool = True) -> None:
    print(f"\n{SEP}\n{BANNER} - demo\n{SEP}")

    print("\n### PART 1 - a real run\n")
    print("One question, the full path: retrieve, reason, use tools, check")
    print("the answer, log the trace.\n")
    if live:
        answer(DEMO_Q)
    else:
        print("  (--dry: skipped, this part costs ~3 requests)")

    print(f"\n\n{SEP}\n### PART 2 - a real failure, and the fix\n{SEP}")
    print("\nWeek 8 found the top failure mode: SKIPPED_STEP. The agent looks")
    print("up the error code, finds a confident-looking chunk, and answers")
    print("WITHOUT searching the policy that lives in another document.")
    print("Week 10 watched it happen live on 2 of 4 questions.")
    print("\nSo: same question, gate OFF. This is the bug, not a story about it.\n")
    if live:
        bad = answer(DEMO_Q, use_gate=False, use_guard=False)
        print("\n\n  Now the same question with week 8's gate ON:\n")
        good = answer(DEMO_Q, use_gate=True, use_guard=True)

        has = lambda r: "cascade" in (r["answer"] or "").lower()
        print(f"\n{SEP}")
        print(f"  gate OFF : mentions cascading? {has(bad)}   "
              f"tools: {', '.join(bad['tools']) or 'none'}   "
              f"${bad['totals']['usd']:.6f}")
        print(f"  gate ON  : mentions cascading? {has(good)}   "
              f"tools: {', '.join(good['tools']) or 'none'}   "
              f"${good['totals']['usd']:.6f}")
        print(f"  the gate rejected an early answer "
              f"{len(good['gated'])} time(s)")
        extra = good['totals']['usd'] - bad['totals']['usd']
        print(f"  price of the fix: ${extra:+.6f} per request")
        print(SEP)
    else:
        print("  (--dry: skipped, this part costs ~6 requests)")

    print(f"\n\n{SEP}\n### PART 3 - a number that improved\n{SEP}")
    _demo_numbers()

    print(f"\n\n{SEP}\n### PART 4 - what is next\n{SEP}")
    print("""
  1. Run the specialists in PARALLEL. Week 10's squad won on quality
     (4/4 vs 2/4) but cost 4.57x the wall-clock, almost all of it
     sequential hand-offs. Parallel would not cut tokens, but it would
     close the latency gap - the one axis where a squad can genuinely
     beat one agent. Untested, so not claimed.

  2. Semantic cache on real traffic, not a built workload. The near-
     duplicate rate in my own log is the number that decides whether it
     is worth shipping, and my log is still too small to trust.

  3. Log rotation and a retention policy. Prompts contain user text, so
     "keep everything forever" becomes a legal problem before it becomes
     a disk problem.

  4. MCP resources and prompts. Week 9 built tools only, over stdio.
     Remote MCP and auth are not built.
""")


def _demo_numbers() -> None:
    """Read the measured numbers out of the result files.

    NOT typed into this file. Week 10 taught me that: I hand-wrote a
    write-up, re-ran the experiment, and shipped a repository whose
    write-up disagreed with its own data. If a file is missing, this says
    so instead of printing a number I cannot back."""
    shown = 0

    race = HERE / "week10" / "race_results.json"
    if race.exists():
        try:
            rows = json.loads(race.read_text(encoding="utf-8"))
            s_pass = sum(1 for r in rows if not (r["single"].get("missing")))
            q_pass = sum(1 for r in rows if not (r["squad"].get("missing")))
            s_usd = sum(r["single"]["usd"] for r in rows)
            q_usd = sum(r["squad"]["usd"] for r in rows)
            s_sec = sum(r["single"]["seconds"] for r in rows)
            q_sec = sum(r["squad"]["seconds"] for r in rows)
            print(f"\n  WEEK 10 - single agent vs 3-agent squad, {len(rows)} questions")
            print(f"    quality      {s_pass}/{len(rows)}  ->  {q_pass}/{len(rows)}")
            print(f"    cost         ${s_usd:.6f}  ->  ${q_usd:.6f}  "
                  f"({q_usd / max(s_usd, 1e-12):.2f}x)")
            print(f"    wall-clock   {s_sec:.1f}s  ->  {q_sec:.1f}s  "
                  f"({q_sec / max(s_sec, 1e-9):.2f}x)")
            print(f"    source: week10/race_results.json")
            shown += 1
        except Exception as e:
            print(f"  week10/race_results.json unreadable: {e}")
    else:
        print("\n  week10/race_results.json MISSING - run: python week10/race.py")

    cost = HERE / "week11" / "logs" / "cost_results.json"
    if cost.exists():
        try:
            d = json.loads(cost.read_text(encoding="utf-8"))
            b, i = d.get("baseline"), d.get("improved")
            if b and i:
                print(f"\n  WEEK 11 - cost per request, before and after")
                print(f"    API calls    {b['api_calls']}  ->  {i['api_calls']}")
                print(f"    per request  ${b['usd_per_request']:.6f}  ->  "
                      f"${i['usd_per_request']:.6f}")
                j = (d.get("justification") or {}).get("real") or {}
                if j:
                    print(f"    BUT on my real logged traffic the near-duplicate")
                    print(f"    rate is only {j['near_rate'] * 100:.0f}%, so the "
                          f"production saving is that,")
                    print(f"    not the workload figure. Both numbers, always.")
                print(f"    source: week11/logs/cost_results.json")
                shown += 1
        except Exception as e:
            print(f"  cost_results.json unreadable: {e}")
    else:
        print("\n  week11 cost results MISSING - run: python week11/cost.py --all")

    reg = HERE / "week11" / "logs" / "regress_results.json"
    if reg.exists():
        try:
            d = json.loads(reg.read_text(encoding="utf-8"))
            res = d["results"]
            done = [r for r in res if r["status"] != "NO DATA"]
            p = sum(1 for r in done if r["status"] == "PASS")
            print(f"\n  WEEK 11 - regression suite ({d['mode']}): {p}/{len(done)} passing")
            for r in res:
                print(f"    {r['id']}  {r['status']:<7} {r['rule'][:46]}")
            print(f"    every case is a failure that really happened")
            print(f"    source: week11/logs/regress_results.json")
            shown += 1
        except Exception as e:
            print(f"  regress_results.json unreadable: {e}")
    else:
        print("\n  week11 regression results MISSING - run: python week11/regress.py")

    if not shown:
        print("\n  NO MEASURED RESULTS ON DISK.")
        print("  I will not invent numbers for a demo. Run the commands above.")


# ======================================================================
def main() -> None:
    ap = argparse.ArgumentParser(
        prog="app.py", description=BANNER,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  python app.py --check
  python app.py "what does ERR-4092 mean on a refund?"
  python app.py "show me how to verify a webhook signature"
  python app.py --repl
  python app.py --eval
  python app.py --demo
  python app.py --demo --dry        the demo script, without spending quota
""")
    ap.add_argument("question", nargs="*", help="the question to answer")
    ap.add_argument("--check", action="store_true", help="preflight only")
    ap.add_argument("--repl", action="store_true", help="interactive")
    ap.add_argument("--eval", action="store_true", help="full suite")
    ap.add_argument("--demo", action="store_true", help="four-part demo")
    ap.add_argument("--dry", action="store_true",
                    help="with --demo: skip the parts that cost quota")
    ap.add_argument("--no-gate", action="store_true",
                    help="disable week 8's required-step gate")
    ap.add_argument("--no-guard", action="store_true",
                    help="disable week 11's output validator")
    ap.add_argument("--json", action="store_true", help="machine-readable")
    args = ap.parse_args()

    if args.check:
        sys.exit(0 if check() else 1)
    if args.eval:
        sys.exit(1 if run_suite() else 0)
    if args.demo:
        demo(live=not args.dry)
        return
    if args.repl:
        repl()
        return

    q = " ".join(args.question).strip()
    if not q:
        ap.print_help()
        print(f"\n{SEP}\nFirst time here?  python app.py --check\n{SEP}")
        return

    try:
        r = answer(q, use_gate=not args.no_gate, use_guard=not args.no_guard,
                   verbose=not args.json)
    except SystemExit as e:
        print(f"\n{e}")
        sys.exit(1)

    if args.json:
        print(json.dumps({k: v for k, v in r.items()}, indent=1))


if __name__ == "__main__":
    main()
