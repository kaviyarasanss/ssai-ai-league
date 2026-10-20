"""
WEEK 11 - THE FIX. An output validator for removed SDK methods.

WHERE THIS CAME FROM
    Not from imagination. From trace r1 in the log: a real answer that
    handed a developer a code sample calling `Webhook.construct_event()`,
    which SDK 3.0 removes and which carries security advisory PP-2025-004.

    The week 8 lesson applies unchanged: you cannot fix a failure you
    cannot DETECT. So detection comes first and the fix is built on top of
    it, rather than hoping better retrieval quietly solves it.

WHY VALIDATION AND NOT "JUST FIX RETRIEVAL"
    Publishing 11_sdk_migration.md makes the right answer FINDABLE. It does
    not make it FOUND. The agent asks for "webhook signature verification",
    and the document that best matches those words is still 07_webhooks.md,
    which still shows the old method. That is the same structural problem
    as week 8's SKIPPED_STEP and week 10's Q1/Q4: the fact that changes the
    answer lives in a document the query does not point at.

    Retrieval tuning is a probability. Validation is a guarantee. For
    something that ships vulnerable code to a developer, I want the
    guarantee.

TWO STAGES, AND ONLY THE FIRST IS FREE
    validate()  pure string check. No model, no network, no cost.
                Runs on EVERY answer.
    repair()    one extra model call, with the migration table injected.
                Runs ONLY when validate() found something.

    So the guard costs nothing on the overwhelming majority of requests
    and one call on the rare bad one. That is the opposite trade from
    week 10's squad, which paid its cost on every single request.
"""
import sys
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from week11 import corpus                                        # noqa: E402

MIGRATION_DOC = HERE / "docs_extra" / "11_sdk_migration.md"


def validate(answer: str) -> list[dict]:
    """Return one violation per removed symbol found. Empty list = clean."""
    out = []
    for sym in corpus.find_deprecated(answer or ""):
        out.append({
            "symbol": sym,
            "replacement": corpus.DEPRECATED[sym],
            "rule": "removed-in-3.0",
            "severity": "high" if sym == "construct_event" else "medium",
        })
    return out


def explain(violations: list[dict]) -> str:
    return "; ".join(f"{v['symbol']} is removed in SDK 3.0 - use "
                     f"{v['replacement']}" for v in violations)


def repair(question: str, answer: str, violations: list[dict]) -> str:
    """Re-ask with the migration table in front of the model.

    Note what is NOT done here: string-replacing `construct_event` with
    `verify_and_parse`. They are not a rename - the replacement takes a
    different argument and has different security behaviour, so a blind
    substitution would produce code that does not run. The model gets the
    migration document and rewrites the sample properly.
    """
    import llm
    migration = MIGRATION_DOC.read_text(encoding="utf-8")
    prompt = (
        f"MIGRATION NOTES:\n{migration}\n\n"
        f"QUESTION: {question}\n\n"
        f"A previous answer was rejected because it used a method that SDK "
        f"3.0 removes: {explain(violations)}.\n\n"
        f"REJECTED ANSWER:\n{answer}\n\n"
        f"Rewrite the answer using the current method. The replacement is "
        f"not a rename - use the correct signature from the migration notes. "
        f"Mention that the old method was removed and why it matters."
    )
    return llm.ask(prompt, temperature=0.0, seed=42, max_tokens=900,
                   system="You correct SDK documentation answers. Be precise "
                          "and brief.")


def answer_with_guard(question: str, verbose: bool = True,
                      require_tools: list | None = None) -> dict:
    """The guarded request path: agent -> validate -> repair if needed.

    TWO DIFFERENT GUARDS, FOR TWO DIFFERENT FAILURES - worth being precise
    about, because they are easy to confuse:

      require_tools   WEEK 8's required-step gate. Fires BEFORE the answer
                      exists: it refuses a FINAL that skipped a lookup.
                      Fixes "the agent never looked" (R2, R3).
      validate()      WEEK 11's output validator. Fires AFTER the answer
                      exists: it refuses an answer containing a removed
                      method. Fixes "the agent looked at a stale page" (R1).

    Neither one can do the other's job. The gate cannot know a method was
    removed; the validator cannot make the agent read a second document.
    """
    from week7.agent import run_agent

    res = run_agent(question, verbose=False, require_tools=require_tools)
    answer = res.get("answer") or ""
    violations = validate(answer)
    repaired = False

    if violations:
        if verbose:
            print(f"    [guard] REJECTED: {explain(violations)}")
        answer = repair(question, answer, violations)
        repaired = True
        violations_after = validate(answer)
        if verbose and violations_after:
            print(f"    [guard] still bad after repair: "
                  f"{explain(violations_after)}")
    else:
        violations_after = []

    return {
        "answer": answer,
        "violations_before": violations,
        "violations_after": violations_after,
        "repaired": repaired,
        "clean": not violations_after,
        "agent": res,
    }
