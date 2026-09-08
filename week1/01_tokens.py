"""
WEEK 1 - EXPERIMENT 1: What a token actually is.

Run:  python week1/01_tokens.py
"""
import tiktoken

# A "tokenizer" is a fixed lookup table built once, before training.
# cl100k_base is the table GPT-4 / GPT-3.5 use. Every model family has its own.
enc = tiktoken.get_encoding("cl100k_base")


def show(text: str) -> None:
    """Print how the tokenizer chops up one piece of text."""
    ids = enc.encode(text)                      # text  -> list of token IDs (ints)
    pieces = [enc.decode([i]) for i in ids]     # each ID -> the text chunk it means
    print(f"  text   : {text!r}")
    print(f"  chars  : {len(text)}   words: {len(text.split())}   TOKENS: {len(ids)}")
    print(f"  pieces : {pieces}")
    print(f"  ids    : {ids}")
    print()


print("=" * 70)
print("1. Common words are cheap. Rare words get shattered.")
print("=" * 70)
show("The payment failed.")     # everyday words -> 1 token each
show("unbelievable")            # 1 word, but not 1 token
show("idempotency")             # rare technical word -> expensive

print("=" * 70)
print("2. IDs and codes are the worst case. Relevant to your day job.")
print("=" * 70)
show("ORD-4471-XZ")             # meaningless to the tokenizer -> many tokens
show("cascading")

print("=" * 70)
print("3. JSON costs more than you think. Braces and quotes are tokens too.")
print("=" * 70)
show('{"status": "settled", "amount": 1499}')

print("=" * 70)
print("4. Non-English text costs several times more per character.")
print("=" * 70)
show("payment failed")
show("பணம் செலுத்துதல் தோல்வி")

print("=" * 70)
print("5. Your actual bill")
print("=" * 70)
doc = open(__file__, encoding="utf-8").read()   # feed this very file to the model
n = len(enc.encode(doc))
# Illustrative rate: $0.15 per 1,000,000 input tokens (a typical cheap model).
rate_per_million = 0.15
print(f"  This script is {len(doc)} characters = {n} tokens")
print(f"  Sending it once as input costs about ${n / 1_000_000 * rate_per_million:.6f}")
print(f"  Sending it 10,000 times costs about ${n / 1_000_000 * rate_per_million * 10_000:.2f}")
print()
print("  Rule of thumb for English: 1 token ~= 4 characters ~= 0.75 words.")
