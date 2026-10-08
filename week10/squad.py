"""
WEEK 10 - THE DOCS SQUAD: one manager, two specialists.

THE PATTERN  (orchestrator-worker)

    manager          reads the question, decides who does what
      |- specialist A   error codes only       (tool: lookup_error_code)
      |- specialist B   policy and prose only  (tool: search_docs)
    manager          composes one answer from their findings

WHY SPECIALISTS ARE NARROW
    A specialist with one tool and one job has a short, unambiguous prompt
    and cannot pick the wrong tool - there is only one. That is the honest
    appeal of the pattern: not "more brains", but "less ambiguity each".

THE HIDDEN COST - this is the point of the week
    Every hand-off RE-SENDS CONTEXT. The manager's plan is re-sent to each
    specialist. Both specialists' findings are re-sent to the manager to
    compose. Nothing is shared memory; it is all re-typed into a new prompt.

    So a 3-agent team does not cost 1x. It costs:
        manager plan            1 call
      + specialist A            1-2 calls, each carrying its own instructions
      + specialist B            1-2 calls, same again
      + manager compose         1 call, carrying BOTH specialists' output
        -------------------------------------------------------------
        4-6 calls, and the compose call is the biggest prompt in the run.

    The single agent from week 7 does the same task in 2-3 calls with one
    growing scratchpad. That is the race.
"""
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from week7.tools import run_tool, init                   # noqa: E402
from week10.meter import metered_ask                     # noqa: E402


# ======================================================================
# THE SPECIALISTS
#
# Each gets ONE tool and one job. The description it sees is its whole
# world - it is not told the other specialist exists.
# ======================================================================
SPECIALISTS = {
    "code_specialist": {
        "tool": "lookup_error_code",
        "brief": "You look up PhoenixPay error codes. You are given ONE "
                 "ERR-#### code. Report exactly what the documentation says "
                 "about it: its meaning, its HTTP status, and whether it is "
                 "retryable. Report only what the lookup returned.",
    },
    "policy_specialist": {
        "tool": "search_docs",
        "brief": "You answer policy and procedure questions from the "
                 "PhoenixPay documentation. You are given ONE question. "
                 "Search the docs and report the relevant policy - exact "
                 "durations, limits and values where the docs give them. "
                 "Report only what the search returned.",
    },
}

SPECIALIST_SYSTEM = """{brief}

You have exactly one tool: {tool}.

Reply in EXACTLY one of these two forms and nothing else.

To use your tool:
THOUGHT: <one sentence>
ACTION: {tool}
ACTION_INPUT: <the input>

To report back:
THOUGHT: <one sentence>
FINAL: <what the documentation says, with the document name in brackets>

Never invent an OBSERVATION - you will be given it."""


def _parse(text: str) -> dict:
    def grab(label):
        m = re.search(rf"^{label}\s*:\s*(.+?)(?=\n[A-Z_]+\s*:|\Z)",
                      text, re.S | re.M)
        return m.group(1).strip() if m else None
    final = grab("FINAL")
    return {"action": grab("ACTION") if not final else None,
            "action_input": grab("ACTION_INPUT") if not final else None,
            "final": final}


def run_specialist(name: str, task: str, verbose: bool = True,
                   max_steps: int = 2) -> dict:
    """A narrow mini-agent: at most one tool call, then report back."""
    spec = SPECIALISTS[name]
    system = SPECIALIST_SYSTEM.format(brief=spec["brief"], tool=spec["tool"])
    scratch, calls, steps = [], 0, []

    for step in range(1, max_steps + 1):
        prompt = (f"TASK: {task}\n\n"
                  + ("\n".join(scratch) + "\n\n" if scratch else "")
                  + "Your turn:")
        raw, tok = metered_ask(prompt, system=system, max_tokens=2000)
        calls += 1
        p = _parse(raw)

        if p["final"]:
            if verbose:
                print(f"      [{name}] -> {' '.join(p['final'].split())[:90]}")
            steps.append({"step": step, "final": p["final"]})
            return {"name": name, "report": p["final"], "calls": calls,
                    "steps": steps}

        if not p["action"]:
            return {"name": name, "report": "(no usable reply)",
                    "calls": calls, "steps": steps}

        # A specialist has exactly one tool, so a wrong name is impossible
        # to act on - we force it to its own tool rather than failing.
        obs = run_tool(spec["tool"], (p["action_input"] or task).strip())
        if verbose:
            print(f"      [{name}] {spec['tool']}("
                  f"{(p['action_input'] or task).strip()[:40]!r})")
        steps.append({"step": step, "action": spec["tool"],
                      "input": p["action_input"], "observation": obs})
        scratch.append(f"ACTION: {spec['tool']}\n"
                       f"ACTION_INPUT: {p['action_input']}\nOBSERVATION: {obs}")

    return {"name": name, "report": "(ran out of steps)", "calls": calls,
            "steps": steps}


# ======================================================================
# THE MANAGER
# ======================================================================
PLAN_SYSTEM = """You are a manager routing work to two specialists.

  code_specialist    looks up ONE ERR-#### error code
  policy_specialist  answers ONE policy or procedure question from the docs

Split the user's question into tasks for them. Reply in EXACTLY this form,
omitting any line you do not need:

CODE_TASK: <a single ERR-#### code, or NONE>
POLICY_TASK: <one question in plain words, or NONE>

Nothing else."""

COMPOSE_SYSTEM = """You write the final answer for the user from your
specialists' reports. Use ONLY what they reported. Be specific - include
exact codes, durations and values. Cite the document names they mentioned.
If the reports do not contain the answer, say so plainly."""


def run_squad(question: str, verbose: bool = True) -> dict:
    """manager plan -> specialists in turn -> manager compose."""
    init()
    started = time.time()
    calls = 0
    tokens = 0
    reports = []

    # ---- 1. PLAN (1 call) --------------------------------------------
    raw, tok = metered_ask(f"QUESTION: {question}\n\nYour plan:",
                           system=PLAN_SYSTEM, max_tokens=500)
    calls += 1
    tokens += tok
    code_task = (re.search(r"^CODE_TASK:\s*(.+)$", raw, re.M) or [None, "NONE"])[1].strip()
    policy_task = (re.search(r"^POLICY_TASK:\s*(.+)$", raw, re.M) or [None, "NONE"])[1].strip()
    if verbose:
        print(f"    manager plan -> code: {code_task} | policy: {policy_task[:50]}")

    # ---- 2. SPECIALISTS ----------------------------------------------
    # Each hand-off re-sends that specialist's full instructions. Nothing
    # is shared; this is where the extra cost comes from.
    if code_task.upper() != "NONE" and re.search(r"ERR-\d{3,4}", code_task.upper()):
        r = run_specialist("code_specialist", code_task, verbose)
        calls += r["calls"]
        reports.append(r)
    if policy_task.upper() != "NONE":
        r = run_specialist("policy_specialist", policy_task, verbose)
        calls += r["calls"]
        reports.append(r)

    # ---- 3. COMPOSE (1 call) -----------------------------------------
    # The biggest prompt in the run: BOTH specialists' reports re-sent.
    body = "\n\n".join(f"=== report from {r['name']} ===\n{r['report']}"
                       for r in reports) or "(no specialist reports)"
    answer, tok = metered_ask(
        f"SPECIALIST REPORTS:\n{body}\n\nUSER QUESTION: {question}\n\nANSWER:",
        system=COMPOSE_SYSTEM, max_tokens=2000)
    calls += 1
    tokens += tok
    if verbose:
        print(f"    manager compose -> {' '.join(answer.split())[:90]}")

    return {"mode": "squad", "question": question, "answer": answer,
            "plan": {"code_task": code_task, "policy_task": policy_task},
            "reports": reports, "llm_calls": calls,
            "seconds": round(time.time() - started, 2),
            "n_agents": 1 + len(reports)}
