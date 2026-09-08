"""
WEEK 6 - The eval set.

An EVAL SET is a list of test cases: a question, plus a way to score the answer.
It is the unit test suite for an app whose output is text.

Every case here carries:
  q        the question
  gold     which document(s) contain the answer
  must     the exact text needed to answer it
  kind     exact_code / semantic / mixed / out_of_scope
  problem  which week-5 problem this case is a REGRESSION TEST for, if any

REGRESSION TESTS FROM FAILURES is the important idea. Week 5 found four named
problems. Each real failure becomes a permanent test, so if a future change
re-breaks it, the suite tells you instead of a user.

  P1  answer is in the right document but its chunk loses the ranking
  P2  citations dropped when the model writes markers as [2, 3]
  P3  an exact identifier lives in an unexpected document
  P4  the user's words do not appear in the documents

Cases with problem=None are the ones that already PASSED in week 5. They are
guards: a change that fixes P1 but breaks these is not an improvement.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from week4.evalset import EVAL_SET, OUT_OF_SCOPE, contains  # noqa: F401

# Which week-5 problem each failing trace belongs to.
# Keyed by question text so the mapping is readable and auditable.
PROBLEM_OF = {
    # P1 - right document, wrong chunk (4 traces: T05, T06, T08, T18)
    "Does ERR-4035 cascade to the next acquirer?": "P1",
    "What is ERR-4003?": "P1",
    "Which decline codes cascade to the next acquirer, and which do not?": "P1",
    "I got a timeout and do not know if the payment went through. What now?": "P1",
    # P2 - citation dropped by our regex (2 traces: T04, T17)
    "How should I back off when I receive ERR-4290?": "P2",
    "What happens if I use a sk_test_ key against live data?": "P2",
    # P3 - identifier in an unexpected document (1 trace: T02)
    "What does ERR-4092 mean?": "P3",
    # P4 - vocabulary gap (1 trace: T15)
    "Why did my payment get rejected for being too small?": "P4",
}


def build_cases() -> list[dict]:
    cases = []
    for i, item in enumerate(EVAL_SET, 1):
        cases.append({
            "id": f"C{i:02d}",
            "q": item["q"],
            "gold": item["gold"],
            "must": item["must"],
            "kind": item["kind"],
            "answerable": True,
            "problem": PROBLEM_OF.get(item["q"]),
        })
    for j, q in enumerate(OUT_OF_SCOPE, 1):
        cases.append({
            "id": f"C{len(EVAL_SET) + j:02d}",
            "q": q, "gold": [], "must": None,
            "kind": "out_of_scope", "answerable": False, "problem": None,
        })
    return cases


CASES = build_cases()

if __name__ == "__main__":
    import collections
    print(f"{len(CASES)} cases")
    print("by kind    :", dict(collections.Counter(c["kind"] for c in CASES)))
    print("by problem :", dict(collections.Counter(c["problem"] or "-none-" for c in CASES)))
    print("\nregression tests from week 5 failures:")
    for c in CASES:
        if c["problem"]:
            print(f"  {c['problem']}  {c['id']}  {c['q'][:60]}")
