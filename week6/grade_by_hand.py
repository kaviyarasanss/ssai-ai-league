"""
WEEK 6 - YOU grade some answers, so the judge can be validated against YOU.

The mentor check is explicit: "If they used an AI judge, did they check it
agrees with their own grading first?"

This is the one part nobody can do for you. An AI judge validated by another
AI is circular. Run this, read 8 answers, press y or n.

    python week6/grade_by_hand.py

For each answer you decide ONE thing:
    Does this answer actually answer the question, given the passages shown?
    y = yes    n = no (wrong, dodged, refused when it should not have)

Takes about 3 minutes. Saves week6/human_grades.json.
"""
import sys, os, json, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results.json")

if not os.path.exists(RESULTS):
    raise SystemExit("Run  python week6/eval.py  first (it writes results.json).")

rows = json.load(open(RESULTS, encoding="utf-8"))["before"]
answerable = [r for r in rows if r["answerable"]]

# A FAIR sample, not the interesting ones: fixed seed so it is reproducible,
# and deliberately mixed so you grade successes as well as failures. Grading
# only the failures would tell you nothing about false alarms.
random.seed(11)
sample = random.sample(answerable, k=min(8, len(answerable)))

print("=" * 74)
print("HUMAN GRADING - 8 answers. y = it answers the question, n = it does not")
print("=" * 74)

grades = {}
for i, r in enumerate(sample, 1):
    print(f"\n[{i}/{len(sample)}]  {r['id']}")
    print(f"Q: {r['q']}")
    print(f"A: {' '.join(r['answer'].split())}")
    while True:
        v = input("   Does this answer the question?  (y/n) > ").strip().lower()
        if v in ("y", "n"):
            break
    grades[r["id"]] = (v == "y")

out = {
    "graded_by": "human",
    "criterion": "does the answer actually answer the question",
    "config": "before (dense only, k=3)",
    "grades": grades,
}
json.dump(out, open(os.path.join(HERE, "human_grades.json"), "w", encoding="utf-8"), indent=1)

yes = sum(grades.values())
print(f"\nsaved week6/human_grades.json   you passed {yes}/{len(grades)}")
print("Now run:  python week6/eval.py --judge --validate")
