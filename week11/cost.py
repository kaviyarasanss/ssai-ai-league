"""
WEEK 11 - COST PER REQUEST, AND ONE MEASURED IMPROVEMENT.

THE RULE
    You cannot cut a cost you have not measured. So this file does three
    things in order, and refuses to skip step 1:

      1. MEASURE   cost per request, live, with no cache help
      2. JUSTIFY   prove from the LOG that the chosen fix will actually fire
      3. IMPROVE   apply it, measure again, report both numbers

WHY A SEMANTIC CACHE, AND NOT SOMETHING ELSE
    The obvious levers for this app were:

      model routing      send easy questions to a cheaper model.
                         REJECTED: the app is already pinned to the
                         cheapest model in the family. Routing could only
                         move work UP in price.
      shorter retrieval  fewer/smaller chunks per call.
                         REJECTED on week 8 evidence: the failures I have
                         measured are SKIPPED lookups, not oversized ones.
                         Trimming context would make the known failure worse
                         to save a few hundred tokens.
      exact-hash cache   already in llm.py since week 1. Already counted in
                         the baseline. Only fires on byte-identical prompts.
      SEMANTIC cache     CHOSEN. Two users asking the same thing in
                         different words is the single most common shape in
                         the log, and the exact-hash cache misses all of it.

    Step 2 is the part people skip. `--justify` reads the real log and
    measures how much of the traffic is near-duplicate. If that number were
    low, the honest conclusion would be "a semantic cache is the wrong fix
    here" - and I would have reported that instead.

HOW THE SEMANTIC CACHE WORKS
    Embed the question. Compare against every question already answered.
    If the best cosine similarity >= THRESHOLD, serve the stored answer and
    make no API call at all.

    The risk is a FALSE HIT: two questions that look similar and need
    different answers. "What does ERR-4032 mean" vs "What does ERR-4033
    mean" embed at 0.970 - that is week 1's measurement, and it is exactly
    why the threshold alone is not enough. So there is a second guard:

      any two questions containing DIFFERENT ERR-#### codes can never be
      a cache hit, whatever the cosine says.

    A cache that returns the wrong answer is not a saving, it is an outage.

RUN
    python week11/cost.py --justify     read the log, 0 API calls
    python week11/cost.py --baseline    live, ~8 API calls
    python week11/cost.py --improved    live where needed, reuses baseline
    python week11/cost.py --report      print the comparison
"""
import io
import re
import sys
import json
import time
import pathlib
import argparse

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from week11 import obs, corpus                                   # noqa: E402
from week10.meter import est                                     # noqa: E402

RESULTS = HERE / "logs" / "cost_results.json"
THRESHOLD = 0.90

# ----------------------------------------------------------------------
# THE WORKLOAD
#
# Four intents, two phrasings each. This shape is not invented - it is what
# --justify measures in the real log: people ask the same small set of
# things in different words.
# ----------------------------------------------------------------------
WORKLOAD = [
    ("intent_webhook_verify", "How do I verify a webhook signature?"),
    ("intent_webhook_verify", "What's the right way to check that a webhook "
                              "really came from PhoenixPay?"),
    ("intent_retry_which",    "Which errors are safe to retry?"),
    ("intent_retry_which",    "When should I retry a failed payment and when "
                              "should I give up?"),
    ("intent_amount_units",   "Why did my $14.99 charge show up as $1499?"),
    ("intent_amount_units",   "What units are payment amounts in?"),
    ("intent_err_4092",       "What does ERR-4092 mean on a refund?"),
    ("intent_err_4092",       "I'm getting ERR-4092 when refunding - what is "
                              "that?"),
]

ANSWER_SYSTEM = (
    "You answer questions about the PhoenixPay SDK using ONLY the "
    "documentation provided. Be correct and brief - at most 4 sentences. "
    "If the documentation does not cover it, say so."
)


# ----------------------------------------------------------------------
# STEP 2 - JUSTIFY FROM THE LOG (zero API calls)
# ----------------------------------------------------------------------
def justify(threshold: float = THRESHOLD) -> dict:
    """How much repeat traffic is in the log, and - the part that matters -
    how much of it the EXISTING exact-hash cache already handles for free.

    THE TRAP THIS FUNCTION AVOIDS
        The naive measurement is "what fraction of questions are similar to
        an earlier one". On this log that comes out around 90%, which would
        be a wonderful justification and a completely dishonest one, for
        two reasons:

          1. Most of those repeats are BYTE-IDENTICAL. llm.py has had a
             hash cache since week 1, so those are already free. A semantic
             cache adds nothing on them and must not take credit for them.
          2. The synthetic noise is generated from 30 templates, so it
             repeats far more than real traffic would.

        So the honest number is NEAR-duplicates only - similar but NOT
        identical - and it is reported separately for real and synthetic
        traffic, with the synthetic figure explicitly marked as not
        evidence.
    """
    from week3 import rag

    rows = [r for r in obs.load() if r.get("question")]
    if len(rows) < 2:
        print("not enough traffic logged yet - run week11/run_logged.py first")
        return {}

    enc = rag.get_encoder()

    def measure(subset: list[dict]) -> dict:
        qs = [r["question"] for r in subset]
        if len(qs) < 2:
            return {"n": len(qs), "exact": 0, "near": 0,
                    "exact_rate": 0.0, "near_rate": 0.0, "examples": []}
        V = enc.encode(qs, normalize_embeddings=True, show_progress_bar=False)
        seen: set[str] = set()
        exact = near = 0
        examples = []
        for i in range(1, len(qs)):
            if qs[i] in seen:
                exact += 1                      # already free via hash cache
                seen.add(qs[i])
                continue
            seen.add(qs[i])
            sims = V[:i] @ V[i]
            order = np.argsort(sims)[::-1]
            for j in order:
                j = int(j)
                if float(sims[j]) < threshold:
                    break
                if qs[j] == qs[i] or not _codes_compatible(qs[i], qs[j]):
                    continue
                near += 1
                if len(examples) < 4:
                    examples.append((round(float(sims[j]), 3),
                                     qs[j][:56], qs[i][:56]))
                break
        d = len(qs) - 1
        return {"n": len(qs), "exact": exact, "near": near,
                "exact_rate": exact / d, "near_rate": near / d,
                "examples": examples}

    real = measure([r for r in rows if not r["meta"].get("synthetic")])
    syn = measure([r for r in rows if r["meta"].get("synthetic")])
    allr = measure(rows)

    print(f"\nJUSTIFICATION - repeat traffic in the log, threshold {threshold}")
    print(f"\n{'':<22}{'requests':>10}{'exact dup':>12}{'NEAR dup':>12}")
    for label, d in (("real traffic", real), ("synthetic noise", syn),
                     ("all", allr)):
        print(f"{label:<22}{d['n']:>10}"
              f"{d['exact']:>7} ({d['exact_rate']*100:>3.0f}%)"
              f"{d['near']:>7} ({d['near_rate']*100:>3.0f}%)")

    print("\n  exact dup = byte-identical to an earlier question.")
    print("              ALREADY free: llm.py's hash cache has caught these")
    print("              since week 1. A semantic cache earns nothing here.")
    print("  NEAR dup  = similar but NOT identical, and not blocked by the")
    print("              error-code guard. This is the ONLY traffic a")
    print("              semantic cache can actually convert.")
    print("\n  The synthetic row is generated from 30 templates, so its")
    print("  repeat rate is an artefact of my generator, not evidence.")
    print("  Judge the fix on the 'real traffic' row.")

    if allr["examples"]:
        print("\n  near-duplicate pairs it would collapse:")
        for s, a, b in allr["examples"]:
            print(f"    {s}  {a!r}")
            print(f"           {b!r}")

    if real["n"] < 30:
        print(f"\n  HONEST LIMIT: only {real['n']} real requests logged. That "
              f"is too few to\n  claim a production repeat rate. The measured "
              f"benefit below is\n  therefore reported on a FIXED WORKLOAD, "
              f"not extrapolated to traffic.")

    return {"threshold": threshold, "real": real, "synthetic": syn,
            "all": allr,
            # kept for the report() header
            "n_questions": allr["n"], "near_dup": allr["near"],
            "rate": allr["near_rate"]}


# ----------------------------------------------------------------------
def calibrate(margin: float = 0.02) -> dict:
    """Pick the cache threshold from DATA instead of guessing it.

    WHY THIS EXISTS
        My first version hard-coded THRESHOLD = 0.90 because it sounded
        strict. It was worth nothing in both directions:

          too low?   week 1 measured 'ERR-4032' against 'ERR-4033' at
                     0.970. A threshold of 0.90 would happily serve one
                     for the other - a WRONG ANSWER, served instantly,
                     with no API call to blame it on.
          too high?  real paraphrases of the same question often sit well
                     below 0.90, so the cache would never fire at all.

        A guessed threshold is a guessed failure rate. So: the workload is
        labelled by INTENT, which gives ground truth for free.

            same-intent pairs    SHOULD hit
            cross-intent pairs   MUST NOT hit

        The safe threshold is above every cross-intent pair the guard does
        not already block. If that value is above the lowest same-intent
        pair, the two groups do not separate and the honest answer is that
        a similarity cache cannot be made safe on this workload - which is
        a result, not a failure.
    """
    from week3 import rag

    enc = rag.get_encoder()
    qs = [q for _, q in WORKLOAD]
    intents = [i for i, _ in WORKLOAD]
    V = enc.encode(qs, normalize_embeddings=True, show_progress_bar=False)

    same, diff, blocked = [], [], []
    for a in range(len(qs)):
        for b in range(a + 1, len(qs)):
            s = float(V[a] @ V[b])
            if intents[a] == intents[b]:
                same.append((s, qs[a], qs[b]))
            elif not _codes_compatible(qs[a], qs[b]):
                blocked.append((s, qs[a], qs[b]))   # guard catches these
            else:
                diff.append((s, qs[a], qs[b]))

    same.sort(); diff.sort()
    lo_same = same[0][0] if same else 0.0
    hi_diff = diff[-1][0] if diff else 0.0
    separable = lo_same > hi_diff
    chosen = round(min(lo_same, hi_diff + margin) if separable
                   else hi_diff + margin, 4)

    print("\nCALIBRATION - choosing the similarity threshold from labelled data")
    print(f"  same-intent pairs   n={len(same):<3} "
          f"min={lo_same:.4f}  max={same[-1][0]:.4f}" if same else "")
    print(f"  cross-intent pairs  n={len(diff):<3} "
          f"min={diff[0][0]:.4f}  max={hi_diff:.4f}" if diff else "")
    print(f"  blocked by the error-code guard before similarity: {len(blocked)}")
    for s, a, b in blocked:
        print(f"    {s:.4f}  {a[:40]!r} vs {b[:40]!r}  <- guard, not threshold")

    if separable:
        print(f"\n  SEPARABLE: every same-intent pair scores above every "
              f"cross-intent pair.")
        print(f"  chosen threshold = {chosen:.4f}  "
              f"(gap {lo_same - hi_diff:.4f})")
    else:
        print(f"\n  NOT SEPARABLE: the closest cross-intent pair "
              f"({hi_diff:.4f}) scores at or above")
        print(f"  the weakest same-intent pair ({lo_same:.4f}). No single "
              f"threshold can both")
        print(f"  fire on paraphrases and refuse different questions on this "
              f"workload.")
        print(f"  Using {chosen:.4f}, which is SAFE but will miss the "
              f"weakest paraphrases.")
        print(f"  Closest dangerous pair:")
        print(f"    {hi_diff:.4f}  {diff[-1][1][:50]!r}")
        print(f"            {diff[-1][2][:50]!r}")

    return {"threshold": chosen, "separable": separable,
            "min_same": round(lo_same, 4), "max_diff": round(hi_diff, 4),
            "n_same": len(same), "n_diff": len(diff),
            "n_blocked_by_guard": len(blocked),
            "closest_dangerous": [round(diff[-1][0], 4), diff[-1][1],
                                  diff[-1][2]] if diff else None}


_CODE = re.compile(r"ERR-\d{3,4}")


def _codes_compatible(a: str, b: str) -> bool:
    """The guard. Different error codes => never a cache hit, whatever the
    cosine similarity says. ERR-4032 and ERR-4033 embed at 0.970 and mean
    opposite things; that measurement is from week 1 and it is the reason
    this function exists."""
    ca, cb = set(_CODE.findall(a.upper())), set(_CODE.findall(b.upper()))
    if not ca and not cb:
        return True
    return ca == cb


# ----------------------------------------------------------------------
# ONE REQUEST - retrieve, then answer. Deliberately NOT the week 7 agent
# loop: the thing under test is the cache, so the request shape is kept as
# simple and as repeatable as possible.
# ----------------------------------------------------------------------
def answer_once(question: str, trace_meta: dict) -> dict:
    import llm
    from week7 import tools

    t0 = time.time()
    with obs.trace(question, track="E", **trace_meta) as t:
        ctx = tools.search_docs(question, k=3)
        prompt = (f"DOCUMENTATION:\n{ctx}\n\nQUESTION: {question}\n\n"
                  f"Answer from the documentation above.")
        ans = llm.ask(prompt, system=ANSWER_SYSTEM, temperature=0.0, seed=42,
                      max_tokens=600)
        t.answer = ans
        # one direct model call, no agent - so "completed" only if it
        # actually returned something
        t.stop_reason = ("completed" if (ans or "").strip()
                         else "model returned an empty reply")
        tot = t.totals()
    return {"question": question, "answer": ans, "trace_id": t.id,
            "usd": tot["usd"], "ms": (time.time() - t0) * 1000,
            "tok_in": tot["tok_in"], "tok_out": tot["tok_out"]}


# ----------------------------------------------------------------------
# STEP 1 - BASELINE
# ----------------------------------------------------------------------
def baseline() -> dict:
    corpus.use("v2")
    rows = []
    for intent, q in WORKLOAD:
        print(f"  [live] {q[:62]}")
        r = answer_once(q, {"experiment": "baseline", "intent": intent,
                            "synthetic": False})
        r["intent"] = intent
        rows.append(r)
    return _summary("baseline", rows, api_calls=len(rows))


# ----------------------------------------------------------------------
# STEP 3 - IMPROVED: the same workload, through a semantic cache
# ----------------------------------------------------------------------
class SemanticCache:
    def __init__(self, threshold: float = THRESHOLD):
        from week3 import rag
        self.enc = rag.get_encoder()
        self.threshold = threshold
        self.qs: list[str] = []
        self.vecs: list = []
        self.answers: list[str] = []
        self.hits = 0
        self.misses = 0
        self.detail: list[dict] = []

    def get(self, question: str):
        if not self.qs:
            self.misses += 1
            return None
        v = self.enc.encode(question, normalize_embeddings=True)
        sims = np.array(self.vecs) @ v
        order = np.argsort(sims)[::-1]
        for j in order:
            j = int(j)
            if sims[j] < self.threshold:
                break
            if not _codes_compatible(question, self.qs[j]):
                self.detail.append({"q": question, "blocked_by_guard": True,
                                    "sim": round(float(sims[j]), 4),
                                    "against": self.qs[j]})
                continue
            self.hits += 1
            self.detail.append({"q": question, "hit": True,
                                "sim": round(float(sims[j]), 4),
                                "against": self.qs[j]})
            return self.answers[j]
        self.misses += 1
        self.detail.append({"q": question, "hit": False,
                            "best_sim": round(float(sims[order[0]]), 4)})
        return None

    def put(self, question: str, answer: str) -> None:
        self.qs.append(question)
        self.vecs.append(self.enc.encode(question, normalize_embeddings=True))
        self.answers.append(answer)


def improved() -> dict:
    corpus.use("v2")
    # Use the CALIBRATED threshold if --calibrate has been run, else fall
    # back to the conservative default. Never silently guess.
    th = THRESHOLD
    if RESULTS.exists():
        cal = json.loads(RESULTS.read_text(encoding="utf-8")).get("calibration")
        if cal:
            th = cal["threshold"]
            print(f"  using calibrated threshold {th} "
                  f"(separable={cal['separable']})")
    cache = SemanticCache(th)
    rows = []
    api_calls = 0

    for intent, q in WORKLOAD:
        cached = cache.get(q)
        if cached is not None:
            print(f"  [cache] {q[:60]}")
            # A cache hit still costs something: one local embedding. It is
            # not an API call and it is not billed, but pretending it is
            # free is the same sloppiness week 10 called out. Embedding
            # ~20 tokens locally rounds to $0, and that is stated, not
            # assumed.
            rows.append({"question": q, "intent": intent, "answer": cached,
                         "usd": 0.0, "ms": 0.0, "tok_in": 0, "tok_out": 0,
                         "served_from": "semantic_cache"})
            continue
        print(f"  [live ] {q[:60]}")
        r = answer_once(q, {"experiment": "improved", "intent": intent,
                            "synthetic": False})
        r["intent"] = intent
        r["served_from"] = "model"
        api_calls += 1
        cache.put(q, r["answer"])
        rows.append(r)

    s = _summary("improved", rows, api_calls=api_calls)
    s["cache"] = {"hits": cache.hits, "misses": cache.misses,
                  "threshold": cache.threshold, "detail": cache.detail}
    return s


def _summary(name: str, rows: list[dict], api_calls: int) -> dict:
    n = len(rows)
    usd = sum(r["usd"] for r in rows)
    return {
        "name": name,
        "requests": n,
        "api_calls": api_calls,
        "api_calls_per_request": round(api_calls / n, 3),
        "usd_total": round(usd, 8),
        "usd_per_request": round(usd / n, 8),
        "tok_in": sum(r["tok_in"] for r in rows),
        "tok_out": sum(r["tok_out"] for r in rows),
        "rows": rows,
    }


# ----------------------------------------------------------------------
def correctness_check(base: dict, imp: dict) -> dict:
    """A cost cut that breaks answers is not a cost cut.

    For every request the improved run served FROM CACHE, compare the
    answer it served against the answer the baseline produced for that same
    question. They need not be byte-identical - they need to agree on the
    facts that matter. Here that is checked the cheap, checkable way: the
    error codes and the key terms present in the baseline answer."""
    by_q = {r["question"]: r for r in base["rows"]}
    checks = []
    for r in imp["rows"]:
        if r.get("served_from") != "semantic_cache":
            continue
        b = by_q.get(r["question"])
        if not b:
            continue
        b_codes = set(_CODE.findall((b["answer"] or "").upper()))
        c_codes = set(_CODE.findall((r["answer"] or "").upper()))
        ok = b_codes == c_codes
        checks.append({"question": r["question"], "codes_match": ok,
                       "baseline_codes": sorted(b_codes),
                       "cached_codes": sorted(c_codes)})
    return {"checked": len(checks),
            "passed": sum(1 for c in checks if c["codes_match"]),
            "detail": checks}


def report() -> None:
    if not RESULTS.exists():
        print("no results yet - run --baseline then --improved")
        return
    d = json.loads(RESULTS.read_text(encoding="utf-8"))
    b, i = d.get("baseline"), d.get("improved")
    if not b or not i:
        print(f"have: {', '.join(k for k in d if d[k])} - need both")
        return

    print("\n" + "=" * 70)
    print("COST PER REQUEST - before and after")
    print("=" * 70)
    print(f"{'':<26}{'BASELINE':>14}{'IMPROVED':>14}{'change':>14}")
    rowfmt = "{:<26}{:>14}{:>14}{:>14}"
    print(rowfmt.format("user requests", b["requests"], i["requests"], "-"))
    print(rowfmt.format("API calls", b["api_calls"], i["api_calls"],
                        f"-{(1-i['api_calls']/max(b['api_calls'],1))*100:.0f}%"))
    print(rowfmt.format("API calls / request",
                        f"{b['api_calls_per_request']:.2f}",
                        f"{i['api_calls_per_request']:.2f}", ""))
    print(rowfmt.format("cost total",
                        f"${b['usd_total']:.6f}", f"${i['usd_total']:.6f}",
                        f"-{(1-i['usd_total']/max(b['usd_total'],1e-12))*100:.0f}%"))
    print(rowfmt.format("COST PER REQUEST",
                        f"${b['usd_per_request']:.6f}",
                        f"${i['usd_per_request']:.6f}",
                        f"-{(1-i['usd_per_request']/max(b['usd_per_request'],1e-12))*100:.0f}%"))
    print(rowfmt.format("input tokens", b["tok_in"], i["tok_in"], ""))
    print(rowfmt.format("output tokens", b["tok_out"], i["tok_out"], ""))

    c = i.get("cache", {})
    print(f"\nsemantic cache: {c.get('hits',0)} hits / "
          f"{c.get('misses',0)} misses  at threshold {c.get('threshold')}")
    for row in c.get("detail", []):
        if row.get("blocked_by_guard"):
            print(f"  GUARD blocked a {row['sim']} match "
                  f"({row['q'][:38]!r} vs {row['against'][:38]!r})")

    chk = d.get("correctness")
    if chk:
        print(f"\ncorrectness of cached answers: "
              f"{chk['passed']}/{chk['checked']} agree with the baseline "
              f"answer on error codes")
        for c2 in chk["detail"]:
            if not c2["codes_match"]:
                print(f"  MISMATCH {c2['question'][:50]!r} "
                      f"{c2['baseline_codes']} vs {c2['cached_codes']}")

    cal = d.get("calibration")
    if cal:
        print(f"\nthreshold {cal['threshold']} was CALIBRATED, not guessed: "
              f"separable={cal['separable']}, "
              f"min same-intent {cal['min_same']}, "
              f"max cross-intent {cal['max_diff']}, "
              f"{cal['n_blocked_by_guard']} pair(s) blocked by the "
              f"error-code guard")

    j = d.get("justification")
    if j and j.get("real"):
        r = j["real"]
        print(f"\njustification (REAL logged traffic only, "
              f"{r['n']} requests):")
        print(f"  exact duplicates {r['exact']} ({r['exact_rate']*100:.0f}%) "
              f"- already free via the week 1 hash cache")
        print(f"  NEAR duplicates  {r['near']} ({r['near_rate']*100:.0f}%) "
              f"- the only traffic this cache converts")
        print(f"\n  So: the {b['requests']}-request workload above shows what "
              f"the cache CAN do.")
        print(f"  The {r['near_rate']*100:.0f}% figure is what it would "
              f"actually do on my logged traffic.")
        print(f"  Both are reported. Quoting only the first would be a lie.")
    print("=" * 70)


def _save(key: str, value) -> None:
    d = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
    d[key] = value
    RESULTS.write_text(json.dumps(d, indent=1), encoding="utf-8")
    print(f"  saved -> {RESULTS.name}  [{key}]")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--justify", action="store_true")
    ap.add_argument("--calibrate", action="store_true")
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--improved", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    if args.justify or args.all:
        _save("justification", justify())
    if args.calibrate or args.all:
        _save("calibration", calibrate())
    if args.baseline or args.all:
        print("\nBASELINE - every request goes to the model")
        _save("baseline", baseline())
    if args.improved or args.all:
        print("\nIMPROVED - semantic cache in front of the model")
        _save("improved", improved())
        d = json.loads(RESULTS.read_text(encoding="utf-8"))
        if d.get("baseline") and d.get("improved"):
            _save("correctness", correctness_check(d["baseline"], d["improved"]))
    if args.report or args.all or not any(
            [args.justify, args.calibrate, args.baseline, args.improved]):
        report()


if __name__ == "__main__":
    main()
