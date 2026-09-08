"""
WEEK 6 - LLM-as-judge, and how to know whether to trust it.

WHY A JUDGE AT ALL
  A rule can check "is a citation present?". A rule cannot check "is this
  answer actually grounded in the passages, or did the model quietly add
  something?". That needs reading. So we use one LLM call to grade another
  LLM's answer.

WHAT WE JUDGE  (the two RAGAS ideas that matter for a docs bot)
  FAITHFULNESS     is every claim supported by the retrieved passages?
                   Catches hallucination.
  ANSWER RELEVANCY does it actually answer the question that was asked?
                   Catches on-topic waffle that dodges the question.

  (RAGAS also defines CONTEXT PRECISION and CONTEXT RECALL, which score the
  retrieval rather than the answer. We already measure those directly in
  week 4 as ANSWER@3, hit-rate@3 and recall@3 - no LLM needed, so no LLM used.)

BINARY, NOT 1-10
  A 1-10 score sounds richer and is mostly noise: nobody, human or model, can
  reliably tell a 6 from a 7, and the same answer drifts between them run to
  run. A binary verdict is reproducible, and a human can agree or disagree
  with it - which is what makes judge validation possible at all.

G-EVAL
  The pattern of giving the judge explicit criteria and asking it to reason
  through them before committing to a verdict. That is what the prompt below
  does: state the rule, apply it, then answer. Reasoning first measurably
  beats asking for a bare verdict.

A DIFFERENT MODEL JUDGES
  The judge runs on GEMINI_JUDGE_MODEL (gemini-3.8-flash), not the workhorse
  that wrote the answer. Two reasons: a model grading its own output is biased
  toward it, and the free tier is per-model, so judging draws on a separate
  daily quota.
"""
import re
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm import ask, JUDGE_MODEL

JUDGE_SYSTEM = """You grade answers produced by a documentation assistant.

You are given the CONTEXT passages the assistant was shown, the QUESTION, and
its ANSWER. Judge two things, strictly.

FAITHFUL: Is every factual claim in the ANSWER supported by the CONTEXT?
  NO if it states anything not present in the context, even if true in general.
  An answer that only says it does not know is FAITHFUL (it claims nothing).

RELEVANT: Does the ANSWER actually answer the QUESTION?
  NO if it is on-topic but dodges what was asked, or answers a different
  question, or is too vague to act on.
  THE TEST: could a developer ACT on this answer without opening the docs
  themselves? If not, RELEVANT is NO.
  NO if it names a mechanism without the specifics needed to use it -
    "use exponential backoff" with no schedule, "use an idempotency key"
    with no explanation of how, "handle the error" with no code.
  NO if the QUESTION asks HOW or HOW LONG or WHICH and the ANSWER gives
    only WHAT.
  Be strict. Most answers that merely sound right fail the act-on-it test.
  Judge each item on its own text - do not reuse a reason across items.
  An answer that says it does not know is NOT RELEVANT when the context does
  contain the answer, and IS RELEVANT when the context genuinely lacks it.

Reason briefly first, then give the verdicts on their own lines.

Reply in exactly this format:
REASONING: <one or two sentences>
FAITHFUL: YES or NO
RELEVANT: YES or NO"""


def judge_answer(question: str, retrieved: list[dict], answer: str,
                 use_cache: bool = True) -> dict:
    """One judging call. Returns {faithful, relevant, reasoning, raw}."""
    passages = "\n\n".join(
        f"[{i}] {c['text']}" for i, c in enumerate(retrieved, 1)
    )
    prompt = (
        f"CONTEXT:\n{passages}\n\n"
        f"QUESTION: {question}\n\n"
        f"ANSWER: {answer}\n"
    )
    raw = ask(prompt, temperature=0.0, seed=7, system=JUDGE_SYSTEM,
              model=JUDGE_MODEL, use_cache=use_cache)

    def flag(name: str):
        m = re.search(rf"{name}\s*:\s*(YES|NO)", raw, re.I)
        return None if not m else m.group(1).upper() == "YES"

    reason = re.search(r"REASONING\s*:\s*(.+)", raw, re.I)
    return {
        "faithful": flag("FAITHFUL"),
        "relevant": flag("RELEVANT"),
        "reasoning": (reason.group(1).strip() if reason else "")[:200],
        "raw": raw,
    }


def agreement(human: dict, judge: dict) -> dict:
    """
    JUDGE VALIDATION.

    Compare the judge's verdicts against a human's on the SAME answers.
    An AI judge nobody checked is just a confident number.

    Reports overall agreement plus the two error directions, which matter
    differently: a judge that is too lenient hides real failures, which is
    far worse than one that is too harsh.
    """
    ids = [k for k in human if k in judge]
    if not ids:
        return {"n": 0}
    agree = sum(1 for k in ids if human[k] == judge[k])
    too_lenient = sum(1 for k in ids if judge[k] and not human[k])
    too_harsh = sum(1 for k in ids if human[k] and not judge[k])
    return {
        "n": len(ids),
        "agreed": agree,
        "agreement": agree / len(ids),
        "judge_too_lenient": too_lenient,
        "judge_too_harsh": too_harsh,
        "disagreed_on": [k for k in ids if human[k] != judge[k]],
    }


# ----------------------------------------------------------------------
# BATCH JUDGING - one call for all cases.
#
# Why: the free tier is ~20 requests/day PER MODEL, and by the time you get
# to judging you may have almost none left. Grading 8 answers in 8 calls is
# the textbook way; grading them in 1 call is the way that actually runs.
#
# Trade-off, stated honestly: the answers share one context window, so a
# batched judge is slightly less independent than 8 separate calls. Each item
# is numbered and judged on its own line to keep them as separate as possible.
# For validating agreement against a human this is an acceptable trade; for a
# production eval you would use one call per item.
# ----------------------------------------------------------------------
BATCH_SYSTEM = """You grade answers produced by a documentation assistant.

For EACH numbered item you are given the CONTEXT passages the assistant saw,
the QUESTION, and its ANSWER. Judge each item completely independently.

FAITHFUL: is every factual claim in the ANSWER supported by that item's CONTEXT?
  An answer that only says it does not know is FAITHFUL (it claims nothing).

RELEVANT: does the ANSWER actually answer the QUESTION?
  NO if it is on-topic but dodges what was asked, answers a different
  question, or is too vague to act on.
  THE TEST: could a developer ACT on this answer without opening the docs
  themselves? If not, RELEVANT is NO.
  NO if it names a mechanism without the specifics needed to use it -
    "use exponential backoff" with no schedule, "use an idempotency key"
    with no explanation of how, "handle the error" with no code.
  NO if the QUESTION asks HOW or HOW LONG or WHICH and the ANSWER gives
    only WHAT.
  Be strict. Most answers that merely sound right fail the act-on-it test.
  Judge each item on its own text - do not reuse a reason across items.
  A refusal is NOT RELEVANT when that item's context does contain the answer,
  and IS RELEVANT when the context genuinely lacks it.

Output one line per item, nothing else, in exactly this format:
<ITEM_ID> | FAITHFUL=YES|NO | RELEVANT=YES|NO | <max 12 word reason>"""


def judge_batch(items: list[dict], use_cache: bool = True) -> dict:
    """
    items: [{"id", "question", "retrieved", "answer"}, ...]
    Returns {id: {faithful, relevant, reasoning}}
    """
    blocks = []
    for it in items:
        passages = "\n".join(
            f"  [{i}] {' '.join(c['text'].split())[:420]}"
            for i, c in enumerate(it["retrieved"], 1)
        )
        blocks.append(
            f"=== ITEM {it['id']} ===\n"
            f"CONTEXT:\n{passages}\n"
            f"QUESTION: {it['question']}\n"
            f"ANSWER: {' '.join(it['answer'].split())}"
        )
    prompt = "\n\n".join(blocks) + (
        f"\n\nNow output exactly {len(items)} lines, one per item."
    )
    raw = ask(prompt, temperature=0.0, seed=7, system=BATCH_SYSTEM,
              model=JUDGE_MODEL, use_cache=use_cache, max_tokens=1200)

    out = {}
    for line in raw.splitlines():
        m = re.match(
            r"\s*(\w+)\s*\|\s*FAITHFUL\s*=\s*(YES|NO)\s*\|\s*RELEVANT\s*=\s*(YES|NO)\s*\|?\s*(.*)",
            line.strip(), re.I)
        if m:
            out[m.group(1).upper()] = {
                "faithful": m.group(2).upper() == "YES",
                "relevant": m.group(3).upper() == "YES",
                "reasoning": m.group(4).strip()[:120],
            }
    return out
