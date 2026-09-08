"""
WEEK 6 - Assertion checks. FREE. No API calls. Run these first.

An ASSERTION CHECK is something a plain rule can decide with no judgement:
"is a source present?", "did it refuse when it should have?". They cost
nothing, never disagree with themselves, and catch most real failures.

The brief is explicit: do these first, they're free. Only reach for an
LLM judge for things a rule genuinely cannot check, like tone or whether an
answer is actually helpful.
"""
import re

REFUSAL_MARKER = "i don't know"


# ----------------------------------------------------------------------
# THE P2 FIX.
#
# old: r"\[(\d+)\]"      matches [2]     but NOT [2, 3]
# new: r"\[([\d,\s]+)\]" matches both, then we pull the digits out
#
# The model wrote "[2, 3]" when one fact came from two passages - which is
# MORE precise, not less. Our parser punished it.
# ----------------------------------------------------------------------
CITATION_OLD = r"\[(\d+)\]"
CITATION_NEW = r"\[([\d,\s]+)\]"


def parse_citations(text: str, n_passages: int, fixed: bool = True) -> list[int]:
    """Pull passage numbers out of an answer. `fixed=False` reproduces the bug."""
    if not fixed:
        found = [int(x) for x in re.findall(CITATION_OLD, text)]
    else:
        found = [int(d) for grp in re.findall(CITATION_NEW, text)
                 for d in re.findall(r"\d+", grp)]
    # A marker pointing at a passage we never sent is invalid - drop it.
    return sorted({n for n in found if 1 <= n <= n_passages})


def run_checks(case: dict, trace: dict, contains_fn, fixed_citations: bool = True) -> dict:
    """
    Score one answer with rules only. Every value is True/False/None.
    None means "not applicable to this kind of case".
    """
    answer = trace["answer"]
    retrieved = trace["retrieved"]
    joined = " ".join(c["text"] for c in retrieved)
    refused = REFUSAL_MARKER in answer.lower()
    cites = parse_citations(answer, len(retrieved), fixed=fixed_citations)

    if case["answerable"]:
        return {
            # Did retrieval put the answer text in front of the model at all?
            "answer_available": contains_fn(joined, case["must"]),
            # Did it refuse even though the answer was reachable?
            "no_false_refusal": not refused,
            # Every answered question must show a source.
            "has_citation": (len(cites) > 0) if not refused else None,
            # Markers must point at passages we actually sent.
            "citations_valid": all(1 <= n <= len(retrieved) for n in cites),
            "refused_correctly": None,
        }
    return {
        "answer_available": None,
        "no_false_refusal": None,
        "has_citation": None,
        "citations_valid": True,
        # Out-of-scope questions MUST be refused. This is the guard that stops
        # "fix the refusals" turning into "answer everything, correctly or not".
        "refused_correctly": refused,
    }
