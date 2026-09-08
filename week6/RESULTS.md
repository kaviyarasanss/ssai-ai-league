# Week 6 — Evals: what we ran, what came out, what it meant

Command: `python week6/eval.py`   (assertion checks: ZERO API calls)
Answer model `gemini-3.5-flash-lite` · 47 chunks · 21 cases · k=3

## The one change under test

| | |
|---|---|
| **BEFORE** | dense-only retrieval, k=3 — exactly the app week 5 traced |
| **AFTER** | + cross-encoder reranking: retrieve 12 with dense, rerank to 3 |

Held constant in both: same chunks (600/100), same k=3 passages into the
prompt, same prompt, temperature 0, seed 42, and the same MIN_SCORE refusal
guard applied to the same dense cosine score.

## Assertion checks — rules only, no LLM

    check                    BEFORE    AFTER    delta
    answer_available          0.667    0.833   +0.167
    no_false_refusal          0.722    0.889   +0.167
    has_citation              0.846    0.938   +0.091
    citations_valid           1.000    1.000   +0.000
    refused_correctly         1.000    1.000   +0.000

Read as counts over the 18 answerable cases:
- answer text reached the model: **12 -> 15**
- false refusals: **5 -> 2**
- out-of-scope still refused: **3/3 -> 3/3**

## Before/after PER PROBLEM TYPE — the week 6 deliverable

    problem                    BEFORE      AFTER
    (previously passing)       13/13       13/13
    P1  wrong chunk             0/4         3/4
    P2  citations dropped       0/2         1/2
    P3  code in odd document    0/1         0/1
    P4  vocabulary gap          0/1         0/1

Two guards held, and they are what make the improvement trustworthy rather
than a trade:
- **13/13 -> 13/13** on cases that already passed. Nothing regressed.
- **refused_correctly 1.000 -> 1.000**. The app got more helpful without
  getting reckless. Without this guard, "answer everything" would score well.

## The citation fix (P2) measured on its own

    BEFORE-config   old regex 11/13   fixed regex 13/13
    AFTER-config    old regex 15/16   fixed regex 16/16

    old: r"\[(\d+)\]"        matches [2]     but NOT [2, 3]
    new: r"\[([\d,\s]+)\]"   matches both

100% citation coverage in both configs. Reported separately so it is never
mixed into the reranking result - two changes measured as two changes.

## Week 5's predictions, scored

Written BEFORE any of this was measured (`week5/TAXONOMY.md`).

| # | prediction | actual | |
|---|---|---|---|
| 1 | P1: 3 of 4 fixed | **3/4** | correct, exactly |
| 2 | P2 untouched by reranking | **0/2 -> 1/2** | **WRONG** |
| 3 | P3 not fixed | 0/1 -> 0/1 | correct |
| 4 | P4 not fixed | 0/1 -> 0/1 | correct |
| 5 | answer_available 0.667 -> ~0.83; refusals 5 -> ~2 | **0.833**; **5 -> 2** | correct, exactly |

**Why prediction 2 was wrong, and why it matters.** Reranking cannot fix a
regex in our own code - that part was right. What it *can* do is change WHICH
passages are retrieved, which changed how the model PHRASED its citations: one
case started emitting `[1]` instead of `[2, 3]`, so the buggy parser happened
to catch it. The bug was not fixed; it was accidentally sidestepped.

A metric can move for reasons unrelated to the mechanism you were targeting.
Measuring per problem type is what exposes that; a single overall score would
have hidden it as "P2 improved".

## Quota engineering (the free tier is ~20 requests/day PER MODEL)

- The week 1 disk cache made the whole 42-answer suite free to re-run:
  `api_calls=0  from_cache=42`.
- Judging was moved to a different model so it draws on a separate daily quota.
- Judging was then narrowed to only the human-graded cases (36 calls -> 8),
  and finally batched into a single call (8 -> 1).

`gemini-3.6-flash`, `3.8-flash` and `3.5-flash` were all exhausted in a day of
building. This is why the cache and the assertion-first design are not
optional niceties.

## A bug caught in the dry run, before any real run

The first version of `eval.py` applied the MIN_SCORE refusal guard to the
BEFORE config only. That silently made it TWO changes and the comparison
worthless. The stub run exposed it: `refused_correctly` went 1.000 -> 0.000.

Rewritten so both configs share one dense first stage, with the guard applied
to the same cosine score. Cross-encoder outputs are unbounded logits, so a
cosine threshold cannot be applied to them - which is precisely why the guard
belongs before reranking, not after.

**An unfair comparison does not announce itself as an error. It produces a
number that looks fine and means nothing.**

## Judge validation — MEASURED

    LLM-AS-JUDGE  (models/gemini-3.5-flash, 8 cases in ONE call)
      faithful 8/8   relevant 8/8

    JUDGE VALIDATION (judge vs human, same 8 answers)
      cases compared     : 8
      agreement          : 75%  (6/8)
      judge too LENIENT  : 2   (missed a real failure)
      judge too HARSH    : 0
      disagreed on       : C15, C04
      -> NOT TRUSTWORTHY - do not report its numbers

    api_calls=1  from_cache=42

**The validation did its job: it caught a bad judge.** The judge passed 8/8 on
relevancy and gave the IDENTICAL one-line reason for six of them ("The answer
is faithful and directly answers the question"). That is the signature of a
judge that is not discriminating. Had we trusted it, the suite would have
reported perfect relevancy on an app with 5 false refusals.

Both disagreements were in the same direction - too LENIENT, never too harsh.
That is the dangerous direction: a lenient judge hides real failures.

### Diagnosing the two disagreements - they differ in kind

**C04 - genuine judge leniency. Fixable.**
Question asks *how* to back off from ERR-4290. Answer: "retry with exponential
backoff". The docs specify 1s, 2s, 4s, 8s, 16s with 30% jitter, plus honouring
`Retry-After`. The human failed it; the judge passed it. The prompt said "too
vague to act on" but never defined actionable.
Fix applied: an explicit act-on-it test plus concrete failing examples.

**C15 - a criterion mismatch, structurally unfixable.**
The judge's own reasoning: *"The context lacks the answer, so the refusal is
relevant."* It applied the rule in its prompt correctly. Given three passages
that do not contain the answer, refusing IS correct generation behaviour.

The human graded end-to-end (the docs DO define ERR-4003 "Amount below
minimum", so the app failed the user). The judge grades generation only,
because it never sees the missing document - by design, so retrieval failures
are not double-counted. **The rules already caught C15** as
`answer_available: False`, so nothing slipped through.

Genuine judge defects: **1 of 8 (88%)** on the criterion the judge can
actually assess. Reported number remains the measured **75%**.

## Original status before the judge ran

Human grades are recorded in `week6/human_grades.json` (6 of 8 passed).
Rubric used: *"does the answer contain what the docs actually specify for the
question asked?"*

    C15  n   docs define ERR-4003 "Amount below minimum (50 minor units)";
             the app refused, so it missed a documented answer
    C18  y   reproduces 01_quickstart's Timeouts sentence verbatim and names
             both documented actions
    C17  y   ERR-4010 stated in two passages; answer names it
    C09  y   both halves: "stored for 24 hours" and "derive from your order ID"
    C14  y   passage shows `if status == "succeeded": fulfil(payment)`
    C10  y   5-second rule, full retry schedule, `undelivered` outcome
    C04  n   question asks HOW to back off; docs specify 1s,2s,4s,8s,16s with
             30% jitter plus honouring Retry-After. The answer gives none of it
    C03  y   "ERR-4013 - key valid but lacks the required permission", verbatim

To finish: `python week6/eval.py --judge --validate` (ONE batched call).
Agreement >= 80% means the judge's numbers can be reported; below that they
cannot. Free quota resets at midnight US Pacific, about 12:30 PM IST.

## Mentor checklist

| check | status |
|---|---|
| Does the test set run with a single command? | YES - `python week6/eval.py` |
| Are last week's real failures included as tests? | YES - 8 regression tests tagged P1-P4 |
| If an AI judge was used, was it checked against your own grading first? | Human grades recorded; agreement pending one call |
| Is there a before-and-after score proving the change helped? | YES - answer_available 0.667 -> 0.833, per problem type, with no regressions |
