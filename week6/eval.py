"""
WEEK 6 - THE ONE COMMAND.

    python week6/eval.py               assertions only, ZERO API calls
    python week6/eval.py --judge       + LLM-as-judge on both configs
    python week6/eval.py --judge --validate   + judge-vs-human agreement

WHAT IT DOES
  Runs every case through the app TWICE:

    BEFORE : the app as week 5 traced it - dense-only retrieval, k=3,
             and the buggy citation parser
    AFTER  : ONE change - cross-encoder reranking (retrieve 12, rerank to 3),
             which is the fix target week 5 chose for problem P1

  Then scores both with rules, optionally with an LLM judge, and prints a
  before/after table PER PROBLEM TYPE.

  The citation regex fix (problem P2) is reported SEPARATELY, as its own
  single change, so it is never confused with the reranking result.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from week3 import rag
from week4 import retrieval
from week6.cases import CASES, contains
from week6.checks import run_checks, parse_citations
from llm import ask, MODEL, JUDGE_MODEL, print_stats

HERE = os.path.dirname(os.path.abspath(__file__))
WANT_JUDGE = "--judge" in sys.argv
WANT_VALIDATE = "--validate" in sys.argv

print(f"Building index...  answer model: {MODEL}")
CHUNKS = rag.build_chunks(chunk_size=600, overlap=100)
MATRIX = rag.embed_chunks(CHUNKS)
print(f"{len(CHUNKS)} chunks\n")


# ----------------------------------------------------------------------
# THE TWO CONFIGURATIONS
# ----------------------------------------------------------------------
def dense_pool(q, k):
    """Shared first stage. Both configs start here, so the MIN_SCORE guard
    below always sees the SAME cosine scale."""
    return rag.search(q, CHUNKS, MATRIX, k=k)


def answer_with(question, use_rerank: bool):
    """
    Reproduces rag.answer(), with exactly ONE thing switchable: reranking.

    Everything else is held constant - same chunks, same k=3 sent to the model,
    same prompt, same temperature and seed, and the same MIN_SCORE refusal
    guard applied to the same dense cosine score. If the guard only applied to
    one config, this would be two changes and the comparison would be worthless.
    """
    pool = dense_pool(question, k=12 if use_rerank else 3)

    # Guard on the DENSE score, identically for both configs. Cross-encoder
    # scores are unbounded logits, so MIN_SCORE (a cosine threshold) cannot be
    # compared against them - which is exactly why the check happens here,
    # before reranking, rather than on the final scores.
    if pool and pool[0]["score"] < rag.MIN_SCORE:
        return {"answer": "I don't know - that is not covered in the documentation.",
                "retrieved": pool[:3]}

    hits = retrieval.rerank(question, pool, k=3) if use_rerank else pool[:3]
    prompt = rag.build_prompt(question, hits)
    text = ask(prompt, temperature=0.0, seed=42, system=rag.SYSTEM)
    return {"answer": text, "retrieved": hits}


def run_config(label, use_rerank, fixed_citations):
    rows = []
    for c in CASES:
        trace = answer_with(c["q"], use_rerank)
        checks = run_checks(c, trace, contains, fixed_citations=fixed_citations)
        rows.append({**c, "answer": trace["answer"], "retrieved": trace["retrieved"],
                     "checks": checks})
        print(f"  [{label}] {c['id']} {c['q'][:52]}")
    return rows


# ----------------------------------------------------------------------
# SCORING
# ----------------------------------------------------------------------
def score(rows, keys):
    """Fraction passed, counting only cases where the check applies."""
    out = {}
    for k in keys:
        vals = [r["checks"][k] for r in rows if r["checks"][k] is not None]
        out[k] = (sum(vals) / len(vals)) if vals else None
    return out


def pass_fail(row):
    """One overall verdict per case: every applicable check must pass."""
    return all(v for v in row["checks"].values() if v is not None)


def by_problem(rows):
    groups = {}
    for r in rows:
        groups.setdefault(r["problem"] or "(previously passing)", []).append(pass_fail(r))
    return {k: (sum(v), len(v)) for k, v in sorted(groups.items())}


print("=" * 78)
print("RUNNING: BEFORE  (dense only, k=3, buggy citation parser)")
print("=" * 78)
before = run_config("before", use_rerank=False, fixed_citations=False)

print()
print("=" * 78)
print("RUNNING: AFTER   (ONE change: + cross-encoder reranking)")
print("=" * 78)
after = run_config("after", use_rerank=True, fixed_citations=False)

KEYS = ["answer_available", "no_false_refusal", "has_citation",
        "citations_valid", "refused_correctly"]

print()
print("=" * 78)
print("ASSERTION CHECKS  (rules only - zero API calls to compute)")
print("=" * 78)
sb, sa = score(before, KEYS), score(after, KEYS)
print(f"{'check':<22} {'BEFORE':>8} {'AFTER':>8} {'delta':>8}")
for k in KEYS:
    b, a = sb[k], sa[k]
    if b is None or a is None:
        continue
    print(f"{k:<22} {b:>8.3f} {a:>8.3f} {a - b:>+8.3f}")

print()
print("=" * 78)
print("BEFORE / AFTER PER PROBLEM TYPE   (cases fully passing)")
print("=" * 78)
pb, pa = by_problem(before), by_problem(after)
print(f"{'problem':<26} {'BEFORE':>10} {'AFTER':>10}")
for k in sorted(set(pb) | set(pa)):
    b, a = pb.get(k, (0, 0)), pa.get(k, (0, 0))
    print(f"{k:<26} {b[0]}/{b[1]:<8} {a[0]}/{a[1]:<8}")

# ----------------------------------------------------------------------
# P2 measured on its own: the citation regex, nothing else changed
# ----------------------------------------------------------------------
print()
print("=" * 78)
print("SEPARATE SINGLE CHANGE: fix the citation parser  (P2)")
print("=" * 78)
for label, rows in (("BEFORE-config", before), ("AFTER-config", after)):
    old = new = total = 0
    for r in rows:
        if not r["answerable"] or "i don't know" in r["answer"].lower():
            continue
        total += 1
        old += 1 if parse_citations(r["answer"], len(r["retrieved"]), fixed=False) else 0
        new += 1 if parse_citations(r["answer"], len(r["retrieved"]), fixed=True) else 0
    print(f"  {label:<14} answers with a citation:  old regex {old}/{total}"
          f"   fixed regex {new}/{total}")

# ----------------------------------------------------------------------
# LLM JUDGE
# ----------------------------------------------------------------------
judged = {}
if WANT_JUDGE:
    from week6.judge import judge_answer, judge_batch, agreement
    print()
    print("=" * 78)
    print(f"LLM-AS-JUDGE  (model: {JUDGE_MODEL})")
    print("=" * 78)
    # QUOTA DISCIPLINE.
    # Judging all 18 answers x 2 configs = 36 calls, and the free tier is
    # ~20/day per model. Validation only needs the cases a human graded, so
    # when human_grades.json exists we judge exactly those. 8 calls, not 36.
    hg_path = os.path.join(HERE, "human_grades.json")
    only = None
    if os.path.exists(hg_path):
        only = set(json.load(open(hg_path, encoding="utf-8"))["grades"])
        print(f"  judging only the {len(only)} human-graded cases "
              f"(free tier is ~20 calls/day/model)\n")

    targets = [r for r in before
               if r["answerable"] and (only is None or r["id"] in only)]
    try:
        # ONE call for all of them - see judge_batch's note on the trade-off.
        verdicts = judge_batch([{"id": r["id"], "question": r["q"],
                                 "retrieved": r["retrieved"],
                                 "answer": r["answer"]} for r in targets])
    except SystemExit as e:
        print(f"  {e}")
        print("  -> no judge quota left on this model. Either set a different")
        print("     GEMINI_JUDGE_MODEL in .env, or wait for the daily reset")
        print("     (midnight US Pacific, about 12:30 PM IST).")
        verdicts = {}

    if verdicts:
        judged["before"] = verdicts
        n = len(verdicts)
        f_ok = sum(1 for v in verdicts.values() if v["faithful"])
        r_ok = sum(1 for v in verdicts.values() if v["relevant"])
        print(f"  judged {n} cases in ONE call")
        print(f"  faithful {f_ok}/{n}   relevant {r_ok}/{n}\n")
        for cid, v in sorted(verdicts.items()):
            print(f"    {cid}  faithful={'Y' if v['faithful'] else 'N'}"
                  f"  relevant={'Y' if v['relevant'] else 'N'}  {v['reasoning']}")

    if WANT_VALIDATE:
        path = os.path.join(HERE, "human_grades.json")
        if not os.path.exists(path):
            print("\n  No human_grades.json - run:  python week6/grade_by_hand.py")
        else:
            human = json.load(open(path, encoding="utf-8"))["grades"]
            jr = {k: v["relevant"] for k, v in judged["before"].items()}
            hr = {k: v["relevant"] for k, v in human.items() if k in jr}
            print()
            print("=" * 78)
            print("JUDGE VALIDATION  (judge vs YOUR grading, same answers)")
            print("=" * 78)
            a = agreement(hr, jr)
            print(f"  cases compared     : {a['n']}")
            print(f"  agreement          : {a['agreement']:.0%}  ({a['agreed']}/{a['n']})")
            print(f"  judge too LENIENT  : {a['judge_too_lenient']}   (missed a real failure)")
            print(f"  judge too HARSH    : {a['judge_too_harsh']}")
            if a["disagreed_on"]:
                print(f"  disagreed on       : {', '.join(a['disagreed_on'])}")
            verdict = ("TRUSTWORTHY" if a["agreement"] >= 0.8 else
                       "NOT TRUSTWORTHY - do not report its numbers")
            print(f"  -> {verdict}")

json.dump({"before": [{k: v for k, v in r.items() if k != "retrieved"} for r in before],
           "after": [{k: v for k, v in r.items() if k != "retrieved"} for r in after]},
          open(os.path.join(HERE, "results.json"), "w", encoding="utf-8"), indent=1)
print("\nsaved: week6/results.json")
print_stats()
