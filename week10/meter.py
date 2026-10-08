"""
WEEK 10 - THE METER: counting tokens and cost honestly.

WHY THIS FILE EXISTS
    The race has to report FOUR numbers: quality, speed, tokens and cost.
    Tokens are the one that is easy to get wrong, for one reason:

        a call served from the llm.py disk cache reports ZERO tokens.

    The cache is a saving in money, not in work. If the squad happened to
    hit more cached prompts than the single agent, a naive count would show
    the squad using fewer tokens - which would be a lie about the thing the
    week is actually measuring.

HOW IT IS HANDLED
    Every call is measured TWO ways and both are reported:

      billed      what the API actually charged this run. Cache hits are 0,
                  because they genuinely cost nothing today.
      work        an estimate of the tokens the prompt and reply represent,
                  cached or not, at the usual ~4 characters per token.

    The RACE is decided on `work`, because that is the real size of the
    conversation each design requires - the thing that would be billed on a
    cold cache, which is what production looks like.

    `billed` is reported alongside so the saving is visible and nobody has
    to guess which number they are looking at.

    Same discipline as week 6's one-sided guard and week 8's trajectory vs
    outcome: name exactly what a number measures, or it will quietly mean
    something else.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import llm                                               # noqa: E402

CHARS_PER_TOKEN = 4          # the usual rough ratio for English + code

# Published rate for the pinned workhorse model, USD per 1M tokens.
# One constant, easy to change, and the cost column is a pure function of
# it - so if the rate is wrong the comparison is still valid, only the
# absolute dollars move.
USD_PER_1M_INPUT = 0.10
USD_PER_1M_OUTPUT = 0.40

meter = {"billed_in": 0, "billed_out": 0, "work_in": 0, "work_out": 0,
         "calls": 0, "cache_hits": 0}


def reset() -> None:
    for k in meter:
        meter[k] = 0


def snapshot() -> dict:
    return dict(meter)


def delta(before: dict) -> dict:
    return {k: meter[k] - before.get(k, 0) for k in meter}


def est(text: str) -> int:
    return max(1, len(text or "") // CHARS_PER_TOKEN)


def _stats() -> dict:
    """llm.stats if the client exposes it; an inert stand-in otherwise, so
    the meter degrades to work-only counting instead of crashing."""
    return getattr(llm, "stats", None) or {"calls": 0, "input_tokens": 0,
                                           "output_tokens": 0}


def metered_ask(prompt: str, system: str = None, **kw) -> tuple:
    """llm.ask, with tokens counted both ways. Returns (text, work_tokens)."""
    st = _stats()
    b_in, b_out = st["input_tokens"], st["output_tokens"]
    b_calls = st["calls"]

    text = llm.ask(prompt, system=system, temperature=0.0, seed=42, **kw)

    st = _stats()
    d_in = st["input_tokens"] - b_in
    d_out = st["output_tokens"] - b_out
    was_cached = st["calls"] == b_calls

    w_in = est(prompt) + est(system)
    w_out = est(text)

    meter["calls"] += 1
    meter["cache_hits"] += 1 if was_cached else 0
    meter["billed_in"] += d_in
    meter["billed_out"] += d_out
    meter["work_in"] += w_in
    meter["work_out"] += w_out
    return text, w_in + w_out


def usd(tok_in: int, tok_out: int) -> float:
    return (tok_in / 1_000_000) * USD_PER_1M_INPUT + \
           (tok_out / 1_000_000) * USD_PER_1M_OUTPUT
