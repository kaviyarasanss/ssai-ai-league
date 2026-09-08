"""
WEEK 1 - EXPERIMENT 2 (v3): What temperature actually controls.

v1 predicted things that turned out false.
v2 was silently invalidated by the response cache - repeated identical calls
   were served from disk, so "all identical? True" proved nothing.
v3 passes use_cache=False wherever we are testing whether repeated calls
   differ. A cache is correct for saving quota and WRONG for this experiment.

Run:  python week1/02_temperature.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm import ask, MODEL, print_stats

print(f"Using model: {MODEL}\n")

PROMPT = "In one short sentence, describe a payment that failed."
RUNS = 2          # keep it to 2 - the free tier is per-day


def repeat(label: str, prediction: str, **kwargs) -> list[str]:
    """
    Call the SAME prompt several times and show whether the answers match.

    use_cache=False is essential here. With the cache on, runs 2..n never
    reach the API at all, so they are identical by construction and the
    test measures nothing.
    """
    answers = [ask(PROMPT, use_cache=False, **kwargs) for _ in range(RUNS)]
    print("=" * 72)
    print(label)
    print(f"   predict: {prediction}")
    print("=" * 72)
    for i, text in enumerate(answers, 1):
        print(f"  run {i}: {text}")
    print(f"  --> all identical? {all(a == answers[0] for a in answers)}\n")
    return answers


a = repeat("A. temperature=0.0, no seed",
           "identical (but on a thinking model it was NOT)",
           temperature=0.0)

b = repeat("B. temperature=0.0, seed=42",
           "identical",
           temperature=0.0, seed=42)

c = repeat("C. temperature=1.8, seed=42",
           "differs from B - same dice, different odds",
           temperature=1.8, seed=42)

print("=" * 72)
print("CROSS-CHECK")
print("=" * 72)
print(f"  A[0] == B[0] ?  {a[0] == b[0]}   (does the seed change the answer?)")
print(f"  B[0] == C[0] ?  {b[0] == c[0]}   (does temperature change the answer?)")
print()
print("  If B == C, temperature did NOT change the output. That happens when")
print("  one continuation is so much likelier than the rest that flattening")
print("  the odds still leaves it on top. Short factual prompts do this.")

print_stats()
