"""
WEEK 10 - THE RACE: squad of three vs the single agent.

    python week10/race.py           both, on the same 4 questions
    python week10/race.py --quiet   numbers only
    python week10/race.py --fresh   ignore the checkpoint and redo

THE EXPERIMENT
    "Multi-agent" is the most hyped idea in AI right now. This runs the
    honest version: build a small team, race it against the single agent on
    exactly the same tests, and keep whichever actually wins.

    Often the single agent wins. That is a result, not a failure - and
    reporting it is the point of the week.

WHY THE COMPARISON IS FAIR
    Same questions, same must-have facts, same tools, same index, same
    model, same process, same meter. The only difference is the control
    flow: one agent with two tools, versus a manager routing to two
    one-tool specialists.

    Week 6's lesson, for the third time: an unfair comparison does not
    announce itself. It produces a number that looks fine and means nothing.

THE FOUR NUMBERS
    quality   required facts present in the final answer
    speed     wall-clock seconds
    tokens    see week10/meter.py - reported as `work` (cache-independent)
              and `billed` (what today actually cost)
    cost      USD from the work tokens, at the rate in meter.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from week4.evalset import contains                       # noqa: E402
from week7.race import QUESTIONS                         # noqa: E402
from week7.tools import init                             # noqa: E402
from week10 import meter                                 # noqa: E402
from week10.squad import run_squad                       # noqa: E402
from llm import MODEL, print_stats                       # noqa: E402

QUIET = "--quiet" in sys.argv
FRESH = "--fresh" in sys.argv
OUT = os.path.join(HERE, "race_results.json")


# ----------------------------------------------------------------------
# The single agent, run through the SAME meter so the token numbers are
# comparable. week7.agent calls llm.ask directly, so we wrap it.
# ----------------------------------------------------------------------
def run_single(question: str, verbose: bool = True) -> dict:
    import week7.agent as agent
    import llm
    real_ask = agent.ask

    def counted(prompt, **kw):
        kw.pop("temperature", None)
        kw.pop("seed", None)
        system = kw.pop("system", None)
        text, _ = meter.metered_ask(prompt, system=system, **kw)
        return text

    agent.ask = counted
    try:
        r = agent.run_agent(question, verbose=verbose)
    finally:
        agent.ask = real_ask
    r["mode"] = "single"
    return r


def score(answer: str, must: list) -> tuple:
    missing = [m for m in must if not contains(answer, m)]
    return (not missing), missing


def run_one(label: str, fn, item: dict) -> dict:
    before = meter.snapshot()
    print(f"\n  --- {label} ---")
    r = fn(item["q"], verbose=not QUIET)
    d = meter.delta(before)
    ok, missing = score(r["answer"], item["must"])
    work_in, work_out = d["work_in"], d["work_out"]
    return {
        **r, "passed": ok, "missing": missing,
        "work_tokens": work_in + work_out,
        "billed_tokens": d["billed_in"] + d["billed_out"],
        "cache_hits": d["cache_hits"],
        "usd": round(meter.usd(work_in, work_out), 6),
    }


def totals(rows: list, key: str) -> dict:
    n = len(rows)
    g = lambda f: sum(r[key][f] for r in rows)
    return {
        "quality": sum(1 for r in rows if r[key]["passed"]) / n,
        "seconds": round(g("seconds"), 1),
        "work_tokens": g("work_tokens"),
        "billed_tokens": g("billed_tokens"),
        "calls": g("llm_calls"),
        "usd": round(sum(r[key]["usd"] for r in rows), 6),
    }


def main() -> None:
    n = init()
    meter.reset()
    print(f"Index ready: {n} chunks · model {MODEL}")
    print("Racing: 1 agent with 2 tools   vs   manager + 2 one-tool specialists")

    done = {}
    if not FRESH and os.path.exists(OUT):
        try:
            done = {r["q"]: r for r in json.load(open(OUT, encoding="utf-8"))}
        except Exception:
            done = {}

    rows = []
    for i, item in enumerate(QUESTIONS, 1):
        if item["q"] in done:
            print(f"\nQ{i}: already recorded - skipping (--fresh to redo)")
            rows.append(done[item["q"]])
            continue

        print("\n" + "=" * 78)
        print(f"Q{i}: {item['q'][:70]}")
        print(f"    required facts: {item['must']}")
        print("=" * 78)

        single = run_one("SINGLE AGENT", run_single, item)
        squad = run_one("SQUAD (manager + 2 specialists)", run_squad, item)

        for nm, r in (("single", single), ("squad", squad)):
            print(f"  {nm:<7} {'PASS' if r['passed'] else 'FAIL'}"
                  f"{'' if r['passed'] else ' missing ' + str(r['missing'])}"
                  f"   {r['llm_calls']} calls"
                  f"   {r['work_tokens']} tok"
                  f"   {r['seconds']}s"
                  f"   ${r['usd']:.6f}")

        rows.append({"q": item["q"], "must": item["must"],
                     "single": single, "squad": squad})
        json.dump(rows, open(OUT, "w", encoding="utf-8"), indent=1)

    # ------------------- the scoreboard -------------------
    s, q = totals(rows, "single"), totals(rows, "squad")

    print("\n" + "=" * 78)
    print("THE RACE - four numbers")
    print("=" * 78)
    print(f"{'':<18}{'SINGLE':>14}{'SQUAD':>14}{'SQUAD / SINGLE':>18}")

    def row(name, key, fmt="{:.3f}", ratio=True):
        a, b = s[key], q[key]
        r = (f"{b/a:.2f}x" if a else "-") if ratio else ""
        print(f"{name:<18}{fmt.format(a):>14}{fmt.format(b):>14}{r:>18}")

    row("quality", "quality", "{:.3f}", ratio=False)
    row("speed (s)", "seconds", "{:.1f}")
    row("tokens (work)", "work_tokens", "{:,}")
    row("cost (USD)", "usd", "${:.6f}")
    calls_x = f"{q['calls'] / s['calls']:.2f}x" if s['calls'] else "-"
    print(f"{'LLM calls':<18}{s['calls']:>14}{q['calls']:>14}{calls_x:>18}")
    print(f"{'billed tokens':<18}{s['billed_tokens']:>14,}{q['billed_tokens']:>14,}"
          f"{'(0 = served from cache)':>26}")

    # ------------------- the verdict -------------------
    print("\n" + "=" * 78)
    print("VERDICT")
    print("=" * 78)
    better_q = q["quality"] - s["quality"]
    cost_x = q["usd"] / s["usd"] if s["usd"] else 0

    if better_q > 0:
        print(f"  The squad answered better: quality {s['quality']:.3f} -> "
              f"{q['quality']:.3f} (+{better_q:.3f}),")
        print(f"  for {cost_x:.2f}x the cost. Worth it only if that quality "
              f"gain matters more")
        print(f"  than paying {cost_x:.1f}x per question - a product "
              f"decision, not a technical one.")
    elif better_q == 0:
        print(f"  SAME QUALITY ({s['quality']:.3f} both), and the squad cost "
              f"{cost_x:.2f}x as much.")
        print(f"  KEEP THE SINGLE AGENT. The team bought nothing and billed "
              f"more for it.")
    else:
        print(f"  The squad answered WORSE: {s['quality']:.3f} -> "
              f"{q['quality']:.3f} ({better_q:.3f}),")
        print(f"  AND cost {cost_x:.2f}x as much. KEEP THE SINGLE AGENT - "
              f"this is the common result,")
        print(f"  and reporting it is the point of the week.")

    print(f"""
  WHY THE SQUAD COSTS MORE - the mechanism, not a guess
    Every hand-off re-sends context. The manager's plan goes out fresh to
    each specialist with that specialist's full instructions attached, and
    both reports come back and are re-sent again in the compose call. There
    is no shared memory between agents - it is all re-typed into new
    prompts. The single agent carries ONE scratchpad that grows.

  WHEN A SQUAD WOULD ACTUALLY BE WORTH IT
    - the parts are genuinely independent and can run IN PARALLEL, so the
      extra tokens buy wall-clock time back (here they ran in sequence)
    - the sub-jobs need clearly different instructions, long enough that
      one prompt holding all of them would confuse the model
    - a specialist needs different permissions - one that can write, one
      that can only read
    - different sub-jobs want different MODELS, cheap for the easy half

  WHEN IT IS NOT
    - a short pipeline you could write down in advance (week 7's lesson)
    - sub-tasks that depend on each other, so they serialise anyway
    - anything where one agent already passes the tests""")

    json.dump(rows, open(OUT, "w", encoding="utf-8"), indent=1)
    print(f"\nsaved: week10/race_results.json")
    print(f"[meter] calls={meter.meter['calls']} "
          f"cache_hits={meter.meter['cache_hits']} "
          f"work={meter.meter['work_in'] + meter.meter['work_out']} tok  "
          f"billed={meter.meter['billed_in'] + meter.meter['billed_out']} tok")
    print_stats()


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        print(f"\nSTOPPED: {e}")
        print("Quota gone. Finished questions are saved - re-run tomorrow.")
        raise
