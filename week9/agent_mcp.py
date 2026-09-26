"""
WEEK 9 - THE AGENT, WITH ITS TOOLS DISCOVERED OVER MCP.

    python week9/agent_mcp.py                       default question
    python week9/agent_mcp.py "your question"

THE DIFFERENCE FROM WEEK 7
    Week 7:  TOOLS = {"search_docs": {...}, "lookup_error_code": {...}}
             A dict I wrote. Adding a tool meant editing the agent.

    Week 9:  TOOLS = discover()
             The agent asks the server what exists, at start-up, and builds
             its own prompt from the descriptions it gets back.

    SEARCH THIS FILE FOR THE NAME OF ANY TOOL IT USES. There isn't one -
    not even in a comment. The agent cannot name a tool it has not yet been
    told about, which is exactly why a new tool on the server needs no
    change here. week9/prove_no_agent_change.py checks that claim
    mechanically: it fails if any discovered tool name appears anywhere in
    this file.

WHERE THE AI RUNS
    Here. This file holds the model call. The MCP server holds no model and
    no key; it just runs functions. The model's only job is choosing WHICH
    tool to call - our code does the calling, exactly as in week 7.
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from llm import ask, MODEL, print_stats                  # noqa: E402
from week9 import mcp_client                             # noqa: E402

DEFAULT_Q = ("We are still on phoenixpay-legacy. Is it safe to stay on it, "
             "and what should we move to?")


# ======================================================================
# BUILD THE PROMPT FROM WHAT THE SERVER SAID
# ======================================================================
def describe(tools: list) -> str:
    """Turn the discovered MCP tool list into the text the model reads.

    The `description` and the `inputSchema` both come off the wire. We are
    not adding knowledge here - we are formatting what the server told us.
    """
    lines = []
    for t in tools:
        args = list((t.get("schema") or {}).get("properties", {}))
        desc = " ".join(t["description"].split())
        lines.append(f"- {t['name']}({', '.join(args)}): {desc}")
    return "\n".join(lines)


def system_prompt(tools: list) -> str:
    return f"""You answer questions using tools, one step at a time.

TOOLS AVAILABLE (discovered from an MCP server at start-up):
{describe(tools)}

On every turn reply in EXACTLY one of these two forms and nothing else.

To use a tool:
THOUGHT: <why you need this, one sentence>
ACTION: <tool name>
ACTION_INPUT: <the single argument value>

To finish:
THOUGHT: <what you now know, one sentence>
FINAL: <the complete answer>

Rules:
- One action per turn. Never invent an OBSERVATION - you will be given it.
- Use only the tool names listed above.
- Answer only from what the tools returned. If they do not contain the
  answer, say so in FINAL.
"""


def _parse(text: str) -> dict:
    def grab(label):
        m = re.search(rf"^{label}\s*:\s*(.+?)(?=\n[A-Z_]+\s*:|\Z)",
                      text, re.S | re.M)
        return m.group(1).strip() if m else None
    final = grab("FINAL")
    return {"thought": grab("THOUGHT"),
            "action": grab("ACTION") if not final else None,
            "action_input": grab("ACTION_INPUT") if not final else None,
            "final": final}


def call_discovered(tools: list, name: str, value: str) -> str:
    """Run a tool by name over MCP. The argument name comes from the schema
    the server published, so we never hard-code it either."""
    spec = next((t for t in tools if t["name"] == name), None)
    if spec is None:
        return (f"No tool named '{name}'. Available: "
                f"{', '.join(t['name'] for t in tools)}.")
    props = list((spec.get("schema") or {}).get("properties", {})) or ["input"]
    try:
        return mcp_client.call_sync(name, {props[0]: value})
    except Exception as e:                       # recoverable, not fatal
        return f"Tool error (recoverable): {e}"


# ======================================================================
# THE LOOP - same shape as week 7, same budgets
# ======================================================================
def run(question: str, max_steps: int = 6, max_seconds: float = 90.0,
        max_calls: int = 8, verbose: bool = True) -> dict:
    tools = mcp_client.discover_sync()
    if verbose:
        print(f"  discovered {len(tools)} tool(s) over MCP: "
              f"{', '.join(t['name'] for t in tools)}\n")

    started, scratchpad, steps = time.time(), [], []
    calls, last_action, stop_reason, answer = 0, None, "completed", None
    SYSTEM = system_prompt(tools)

    for step_no in range(1, max_steps + 1):
        if time.time() - started > max_seconds:
            stop_reason = f"time budget exceeded ({max_seconds}s)"
            break
        if calls >= max_calls:
            stop_reason = f"call budget exceeded ({max_calls} calls)"
            break

        prompt = (f"QUESTION: {question}\n\n"
                  + ("\n".join(scratchpad) + "\n\n" if scratchpad else "")
                  + "Your turn:")
        raw = ask(prompt, temperature=0.0, seed=42, system=SYSTEM,
                  max_tokens=2000)
        calls += 1
        if not raw.strip() and calls < max_calls:        # week 7's fix
            raw = ask(prompt + "\n\nReply now, in the required format, "
                               "starting with THOUGHT:",
                      temperature=0.0, seed=43, system=SYSTEM, max_tokens=4000)
            calls += 1
        if not raw.strip():
            stop_reason = "model returned an empty reply"
            break

        p = _parse(raw)
        if verbose and p["thought"]:
            print(f"  step {step_no}")
            print(f"    THOUGHT: {' '.join(p['thought'].split())[:110]}")

        if p["final"]:
            answer = p["final"]
            steps.append({"n": step_no, "thought": p["thought"], "final": answer})
            if verbose:
                print(f"    FINAL:   {' '.join(answer.split())[:110]}")
            break

        if not p["action"]:
            stop_reason = "model reply was malformed (no ACTION and no FINAL)"
            break

        action, value = p["action"].strip(), (p["action_input"] or "").strip()
        if (action, value) == last_action:
            stop_reason = "repeated the same action twice - stuck"
            break
        last_action = (action, value)

        obs = call_discovered(tools, action, value)
        if verbose:
            print(f"    ACTION:  {action}({value!r})   [over MCP]")
            print(f"    OBSERVE: {' '.join(obs.split())[:110]}...")
        steps.append({"n": step_no, "thought": p["thought"], "action": action,
                      "input": value, "observation": obs})
        scratchpad.append(f"THOUGHT: {p['thought']}\nACTION: {action}\n"
                          f"ACTION_INPUT: {value}\nOBSERVATION: {obs}")
    else:
        stop_reason = f"step budget exceeded ({max_steps} steps)"

    return {"question": question, "answer": answer or "(no answer)",
            "tools_discovered": [t["name"] for t in tools],
            "steps": steps, "n_steps": len(steps), "llm_calls": calls,
            "seconds": round(time.time() - started, 2),
            "stop_reason": stop_reason}


def main() -> None:
    q = " ".join(a for a in sys.argv[1:] if not a.startswith("--")) or DEFAULT_Q
    print("=" * 78)
    print("WEEK 9 - AGENT WITH MCP-DISCOVERED TOOLS")
    print("=" * 78)
    print(f"  model: {MODEL}")
    print(f"  question: {q}\n")
    r = run(q)
    print("\n" + "-" * 78)
    print(f"  stop_reason : {r['stop_reason']}")
    print(f"  steps/calls : {r['n_steps']} / {r['llm_calls']}   ({r['seconds']}s)")
    print(f"  tools used  : discovered at runtime, none hard-coded in this file")
    json.dump(r, open(os.path.join(HERE, "agent_mcp_run.json"), "w",
                      encoding="utf-8"), indent=1)
    print("\nsaved: week9/agent_mcp_run.json")
    print_stats()


if __name__ == "__main__":
    main()
