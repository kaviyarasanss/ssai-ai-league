"""
WEEK 7 - The same task as a FIXED WORKFLOW.

No LLM decides anything about control flow. The steps are hardcoded because
for this task shape we already know them:

    1. regex the question for an ERR-#### code        (no LLM)
    2. if found, exact-lookup that code               (no LLM)
    3. semantic search on the question itself         (no LLM)
    4. ONE LLM call to compose the answer from both

That is 1 LLM call, always. The agent needs 3-5 and can loop.

WHEN THE FIXED VERSION IS THE RIGHT CHOICE: when you already know the steps.
It is faster, cheaper, and cannot loop forever. An agent earns its cost only
when the path genuinely depends on what it finds.
"""
import re
import time
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm import ask
from week7.tools import search_docs, lookup_error_code, init

SYSTEM = """You answer questions about the PhoenixPay SDK using ONLY the
context provided. Cite the document names you relied on, in square brackets.
If the context does not contain the answer, say so plainly. Be specific -
include exact codes, durations and values where the context gives them."""


def run_workflow(question: str, verbose: bool = True) -> dict:
    init()
    started = time.time()
    steps = []
    context_parts = []

    # STEP 1 - find a code. Plain regex, no model needed.
    codes = re.findall(r"ERR-\d{3,4}", question.upper())
    steps.append({"n": 1, "step": "regex scan for ERR-#### codes",
                  "result": codes or "none found"})
    if verbose:
        print(f"  step 1  regex scan -> {codes or 'no codes'}")

    # STEP 2 - exact lookup for each code found.
    for code in codes:
        out = lookup_error_code(code)
        context_parts.append(f"=== exact lookup: {code} ===\n{out}")
        steps.append({"n": 2, "step": f"lookup_error_code({code})",
                      "result": out[:120]})
        if verbose:
            print(f"  step 2  lookup_error_code({code})")

    # STEP 3 - semantic search on the question as written.
    docs = search_docs(question, k=3)
    context_parts.append(f"=== semantic search ===\n{docs}")
    steps.append({"n": 3, "step": "search_docs(question)", "result": docs[:120]})
    if verbose:
        print(f"  step 3  search_docs(question)")

    # STEP 4 - one composition call.
    prompt = ("CONTEXT:\n" + "\n\n".join(context_parts)
              + f"\n\nQUESTION: {question}\n\nANSWER:")
    answer = ask(prompt, temperature=0.0, seed=42, system=SYSTEM, max_tokens=700)
    steps.append({"n": 4, "step": "compose answer (1 LLM call)", "result": answer[:120]})
    if verbose:
        print(f"  step 4  compose -> {' '.join(answer.split())[:100]}")

    return {
        "mode": "workflow",
        "question": question,
        "answer": answer,
        "steps": steps,
        "n_steps": len(steps),
        "llm_calls": 1,
        "seconds": round(time.time() - started, 2),
        "stop_reason": "fixed sequence - cannot loop",
    }
