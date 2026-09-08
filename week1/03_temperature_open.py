"""
WEEK 1 - EXPERIMENT 3: Temperature, with a prompt that can actually show it.

Experiment 2 used "describe a payment that failed" and temperature appeared
to do NOTHING - temp 0 and temp 1.8 gave the same sentence.

That was not a broken setting. It was a badly chosen prompt.

  "describe a payment that failed"  -> one continuation dominates
                                       ("declined due to insufficient funds").
                                       Flattening the odds still leaves it on
                                       top, so the output never changes.

  "invent a name for a coffee shop" -> thousands of equally good continuations.
                                       No dominant winner. Now flattening the
                                       odds genuinely changes what comes out.

Temperature can only reveal itself when the model is UNCERTAIN.

Run:  python week1/03_temperature_open.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm import ask, MODEL, print_stats

print(f"Using model: {MODEL}\n")

CLOSED = "In one short sentence, describe a payment that failed."
OPEN = "Invent a name for a coffee shop. Reply with the name only, nothing else."


def trial(prompt: str, temperature: float, runs: int) -> None:
    # use_cache=False: we are measuring variation, so identical inputs must
    # actually reach the API instead of being served from disk.
    answers = [ask(prompt, temperature=temperature, use_cache=False)
               for _ in range(runs)]
    unique = len(set(answers))
    print(f"  temperature={temperature}  ({runs} runs)")
    for i, text in enumerate(answers, 1):
        print(f"    {i}. {text}")
    print(f"    --> {unique} unique answer(s) out of {runs}\n")


print("=" * 72)
print("CLOSED QUESTION - one obvious answer")
print(f"  {CLOSED}")
print("=" * 72)
trial(CLOSED, temperature=1.8, runs=2)
print("  Already shown at temp 0: same sentence. High temp changes nothing")
print("  because there is nothing to change it TO.\n")

print("=" * 72)
print("OPEN QUESTION - thousands of equally good answers")
print(f"  {OPEN}")
print("=" * 72)
trial(OPEN, temperature=0.0, runs=2)
trial(OPEN, temperature=1.8, runs=3)

print("=" * 72)
print("WHAT TO CONCLUDE")
print("=" * 72)
print("  Temperature does not make a model 'more creative'. It widens the")
print("  net around what the model already thinks is likely. If the model is")
print("  certain, a wider net catches the same fish.")
print()
print("  This is why RAG answers use temp 0: once the right document is in")
print("  front of it, the model SHOULD be certain, and variety is a bug.")

print_stats()
