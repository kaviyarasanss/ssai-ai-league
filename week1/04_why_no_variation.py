"""
WEEK 1 - EXPERIMENT 4: Why does temperature appear to do nothing?

Observed: gemini-3.5-flash-lite returns "Velvet Bean" every time, even at
temperature 1.8 on a deliberately open-ended prompt. That should not happen
if the model is sampling.

Four possible explanations. Each test rules one in or out.

  H1  top_p is filtering the candidates down to one before temperature
      ever gets a say. -> set top_p=1.0, top_k high, and retest.

  H2  The model ignores temperature entirely (some fast/lite models are
      served with fixed greedy decoding). -> if H1 fails too, suspect this.

  H3  Something in OUR request is pinning it - e.g. thinking_config.
      -> send a bare request with no config at all.

  H4  It is model-specific. -> run the identical test on another model.

Costs ~9 API calls, spread over two models.
Run:  python week1/04_why_no_variation.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm import ask, MODEL, JUDGE_MODEL, print_stats

OPEN = "Invent a name for a coffee shop. Reply with the name only, nothing else."


def trial(label: str, runs: int = 3, **kwargs) -> None:
    answers = []
    for _ in range(runs):
        try:
            answers.append(ask(OPEN, use_cache=False, **kwargs))
        except Exception as e:
            answers.append(f"[ERROR] {' '.join(str(e).split())[:90]}")
    unique = len(set(answers))
    flag = "VARIES" if unique > 1 else "same  "
    print(f"  {flag}  {label}")
    for a in answers:
        print(f"           {a}")
    print()


print(f"Workhorse: {MODEL}\nJudge:     {JUDGE_MODEL}\n")

print("=" * 72)
print("H1: is top_p filtering candidates down to one?")
print("=" * 72)
trial("temp=2.0, top_p=1.0, top_k=200", temperature=2.0, top_p=1.0, top_k=200)

print("=" * 72)
print("H2/H3: does a different SEED change the answer?")
print("   If sampling is happening at all, different seeds must diverge.")
print("=" * 72)
seeds = [1, 500, 99999]
answers = [ask(OPEN, temperature=2.0, seed=s, use_cache=False) for s in seeds]
for s, a in zip(seeds, answers):
    print(f"           seed={s:<6} -> {a}")
print(f"  {'VARIES' if len(set(answers)) > 1 else 'same  '}  "
      f"{len(set(answers))} unique across {len(seeds)} seeds\n")

print("=" * 72)
print("H4: is it specific to this model?")
print("=" * 72)
trial(f"temp=2.0 on {JUDGE_MODEL}", runs=3, temperature=2.0, model=JUDGE_MODEL)

print("=" * 72)
print("HOW TO READ THIS")
print("=" * 72)
print("  Any block marked VARIES = sampling works, and whatever that block")
print("  changed is what was suppressing it.")
print("  All blocks 'same' on the workhorse but VARIES on the judge model")
print("  = the lite model is served with fixed decoding. Not our bug.")
print("  Everything 'same' everywhere = the API is deduplicating responses.")
print_stats()
