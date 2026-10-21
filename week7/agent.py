"""
WEEK 7 - The agent loop, hand-built. About 80 lines of actual loop.

THE LOOP (ReAct: Reason + Act)

    while not done:
        THOUGHT      the model says why it is doing the next thing
        ACTION       the model names a tool and its input
        OBSERVATION  WE run the tool and paste the result back
    FINAL            the model answers

The model never runs anything. It emits text naming a tool; our code executes
it. Same rule as week 2 tool calling - only here we drive the loop ourselves
instead of letting the SDK hide it.

STOP CONDITIONS AND BUDGETS - an agent without these can loop forever and
bill you for it. We enforce four:
    max_steps     hard cap on iterations
    max_seconds   wall-clock cap
    max_calls     LLM call cap
    repeat guard  the same action twice in a row means it is stuck

MEMORY
    short-term  the scratchpad below - thoughts, actions, observations
    long-term   not needed for a single task. Would be a vector store or
                mem0, keyed by user, surviving across tasks.
    summarisation memory  when the scratchpad grows past a threshold we
                compress the oldest steps into one summary line rather than
                dropping them - that is what keeps a long task inside the
                context window.
"""
import re
import time
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm import ask
from week7.tools import run_tool, tool_descriptions, init

SYSTEM = f"""You answer questions about the PhoenixPay SDK by using tools, one
step at a time.

TOOLS AVAILABLE:
{tool_descriptions()}

On every turn reply in EXACTLY one of these two forms and nothing else.

To use a tool:
THOUGHT: <why you need this, one sentence>
ACTION: <tool name>
ACTION_INPUT: <the input>

To finish:
THOUGHT: <what you now know, one sentence>
FINAL: <the complete answer, citing the document names you relied on>

Rules:
- One action per turn. Never invent an OBSERVATION - you will be given it.
- If the question mentions an ERR-#### code, look that code up FIRST.
- Do not repeat an action you have already done.
- Answer only from what the tools returned. If the tools do not contain the
  answer, say so in FINAL.
"""


# How many output tokens one agent turn may use. This is NOT just the visible
# reply: on a thinking model the hidden reasoning tokens come out of the same
# budget. 700 was too tight - it produced empty replies on the harder
# questions in the first live race. See week7/RESULTS.md.
#
# WEEK 12 - why this is now configurable, and why the DEFAULT IS UNCHANGED.
#
#   Week 12 integration testing found a seam: week 8's required-step gate
#   and this budget interact badly. When the gate rejects a FINAL it appends
#   an OBSERVATION explaining what was skipped, which makes the next prompt
#   LONGER. On a hard question that extra context pushed the model over the
#   edge: it spent the entire 2000-token budget thinking and returned an
#   empty reply - twice, including the retry - so the request produced NO
#   ANSWER AT ALL. Measured live: trace tr_d17dd94cebc5, steps 4 and 5,
#   tok_out = 0 on both.
#
#   Neither fix is wrong on its own. The gate was measured in week 8 on
#   SHORTER prompts, where this never happened. That is what an integration
#   seam looks like.
#
#   The default stays 2000 so weeks 7, 8 and 10 reproduce EXACTLY as
#   measured. Week 11 raises it via the environment variable, because its
#   requests run with the gate on and therefore carry longer prompts.
REPLY_TOKENS = int(os.environ.get("AGENT_REPLY_TOKENS", "2000"))


def _parse(text: str) -> dict:
    """Pull the structured fields out of the model's reply."""
    def grab(label):
        m = re.search(rf"^{label}\s*:\s*(.+?)(?=\n[A-Z_]+\s*:|\Z)",
                      text, re.S | re.M)
        return m.group(1).strip() if m else None

    final = grab("FINAL")
    return {
        "thought": grab("THOUGHT"),
        "action": grab("ACTION") if not final else None,
        "action_input": grab("ACTION_INPUT") if not final else None,
        "final": final,
    }


def run_agent(question: str, max_steps: int = 6, max_seconds: float = 90.0,
              max_calls: int = 8, verbose: bool = True,
              require_tools: list | None = None, max_gate_pushes: int = 2) -> dict:
    """
    Run the loop. Returns a trace: every step, the stop reason, and the answer.
    """
    init()
    started = time.time()
    scratchpad: list[str] = []
    steps: list[dict] = []
    calls = 0
    last_action = None
    gate_pushes = 0
    gated: list[dict] = []
    stop_reason = "completed"
    answer = None

    for step_no in range(1, max_steps + 1):

        # --- budget checks BEFORE spending anything ------------------
        if time.time() - started > max_seconds:
            stop_reason = f"time budget exceeded ({max_seconds}s)"
            break
        if calls >= max_calls:
            stop_reason = f"call budget exceeded ({max_calls} calls)"
            break

        # --- summarisation memory: compress old steps ----------------
        if len(scratchpad) > 6:
            head = "\n".join(scratchpad[:-4])
            summary = ask(
                f"Compress these agent steps into 2 short lines of facts "
                f"learned:\n\n{head}",
                temperature=0.0, seed=1, max_tokens=200)
            calls += 1
            scratchpad = [f"EARLIER (summarised): {summary}"] + scratchpad[-4:]
            if verbose:
                print("      [memory] compressed older steps")

        prompt = (f"QUESTION: {question}\n\n"
                  + ("\n".join(scratchpad) + "\n\n" if scratchpad else "")
                  + "Your turn:")

        raw = ask(prompt, temperature=0.0, seed=42, system=SYSTEM,
                  max_tokens=REPLY_TOKENS)
        calls += 1

        # --- empty reply: the thinking tokens ate the budget ----------
        # MEASURED in the first live race: 2 of 4 agent runs died here.
        # max_output_tokens caps VISIBLE + HIDDEN thinking tokens together,
        # so a hard question can spend the whole budget thinking and return
        # an empty string. That is week 1's hidden-thinking-tokens lesson
        # showing up as a control-flow bug. Retry ONCE with double the
        # budget and an explicit format reminder before giving up.
        if not raw.strip() and calls < max_calls:
            if verbose:
                print("      [retry] empty reply - retrying with 2x token budget")
            raw = ask(prompt + "\n\nReply now, in the required format, "
                               "starting with THOUGHT:",
                      temperature=0.0, seed=43, system=SYSTEM,
                      max_tokens=REPLY_TOKENS * 2)
            calls += 1

        if not raw.strip():
            # WEEK 12 - this message used to assert "output budget consumed
            # by thinking tokens" for EVERY empty reply. That is true of some
            # and false of others. Week 7 measured the budget as the cause at
            # 700 tokens. But the ERR-4033 request in the gate case came back
            # empty at 2000/4000 and again at 6000/12000, so there a bigger
            # budget did not help. One message prints for all of them, so
            # it claims only what was measured, scoped to where it was
            # measured.
            stop_reason = (
                "model returned an empty reply - cause not established. "
                "A bigger budget did not help in the measured gate case "
                "(empty at 2000/4000 and at 6000/12000 tokens: "
                "tr_d17dd94cebc5, tr_8f2e7869659d).")
            steps.append({"n": step_no, "raw": ""})
            break

        parsed = _parse(raw)

        if verbose:
            print(f"  step {step_no}")
            if parsed["thought"]:
                print(f"    THOUGHT: {' '.join(parsed['thought'].split())[:110]}")

        # --- the model wants to finish -------------------------------
        if parsed["final"]:
            # WEEK 8 FIX - the required-step gate.
            #
            # The week 8 trajectory audit found SKIPPED_STEP as the top
            # failure: the agent answered after one tool call when the task
            # needed two, and was RIGHT anyway because the one chunk it read
            # happened to contain both facts. A lucky path.
            #
            # So before accepting FINAL we check the required tools were
            # actually used. If not, we do not accept the answer - we tell
            # the agent what it skipped and let it carry on. Bounded by
            # max_gate_pushes so the gate itself cannot cause a loop.
            #
            # require_tools=None reproduces week 7 behaviour exactly, which
            # is what makes the before/after comparison fair: ONE variable.
            missing = [t for t in (require_tools or [])
                       if t not in [s.get("action") for s in steps]]
            if missing and gate_pushes < max_gate_pushes:
                gate_pushes += 1
                gated.append({"step": step_no, "missing": list(missing)})
                if verbose:
                    print(f"    [gate] FINAL rejected - never called "
                          f"{', '.join(missing)}")
                scratchpad.append(
                    f"THOUGHT: {parsed['thought']}\nFINAL: {parsed['final']}\n"
                    f"OBSERVATION: Your answer was NOT accepted. This task "
                    f"requires you to use {', '.join(missing)} before "
                    f"answering, and you have not. Use it now, then answer."
                )
                continue

            answer = parsed["final"]
            steps.append({"n": step_no, "thought": parsed["thought"], "final": answer})
            if verbose:
                print(f"    FINAL:   {' '.join(answer.split())[:110]}")
            break

        # --- malformed reply ----------------------------------------
        if not parsed["action"]:
            stop_reason = "model reply was malformed (no ACTION and no FINAL)"
            steps.append({"n": step_no, "raw": raw[:200]})
            break

        action = parsed["action"].strip()
        action_input = (parsed["action_input"] or "").strip()

        # --- repeat guard: identical action means it is stuck --------
        if (action, action_input) == last_action:
            stop_reason = "repeated the same action twice - stuck"
            steps.append({"n": step_no, "action": action, "input": action_input,
                          "observation": "(blocked: repeat)"})
            break
        last_action = (action, action_input)

        observation = run_tool(action, action_input)
        if verbose:
            print(f"    ACTION:  {action}({action_input!r})")
            print(f"    OBSERVE: {' '.join(observation.split())[:110]}...")

        steps.append({"n": step_no, "thought": parsed["thought"], "action": action,
                      "input": action_input, "observation": observation})
        scratchpad.append(
            f"THOUGHT: {parsed['thought']}\nACTION: {action}\n"
            f"ACTION_INPUT: {action_input}\nOBSERVATION: {observation}"
        )
    else:
        stop_reason = f"step budget exceeded ({max_steps} steps)"

    return {
        "mode": "agent",
        "question": question,
        "answer": answer or "(no answer - stopped early)",
        "steps": steps,
        "n_steps": len(steps),
        "llm_calls": calls,
        "seconds": round(time.time() - started, 2),
        "stop_reason": stop_reason,
        "required_tools": require_tools or [],
        "gate_pushes": gate_pushes,
        "gated": gated,
    }
