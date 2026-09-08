"""
Shared LLM helper. Every week imports from here.

Why one shared file instead of copy-pasting the client into each script?
  1. The model is pinned in ONE place (.env) - Week 6 evals need that stability.
  2. Retry logic lives in ONE place - free tier throttles, and Google's
     servers occasionally return 503 when busy.
  3. Call counting lives in ONE place - so you know what an eval run costs.

Usage:
    from llm import ask, MODEL, print_stats
    answer = ask("Say hello", temperature=0.0, seed=42)
"""
import os
import json
import time
import hashlib
import logging
import pathlib
import warnings

from dotenv import load_dotenv
from google import genai
from google.genai import types

warnings.filterwarnings("ignore")
# The SDK logs an "automatic function calling (AFC)" notice on every call.
# Irrelevant unless you are doing tool calling (Week 2). Silence it.
logging.getLogger("google_genai").setLevel(logging.ERROR)
logging.getLogger("google_genai.models").setLevel(logging.ERROR)

load_dotenv()

_api_key = os.environ.get("GEMINI_API_KEY")
if not _api_key:
    raise SystemExit("No GEMINI_API_KEY. Copy .env.example to .env and paste your key.")

_client = genai.Client(api_key=_api_key)

# Two models, two jobs. The free tier is per-day PER MODEL, so splitting
# work across models also splits the quota - and the cheap one does the bulk.
MODEL = os.environ.get("GEMINI_MODEL", "models/gemini-3.5-flash-lite")
JUDGE_MODEL = os.environ.get("GEMINI_JUDGE_MODEL", "models/gemini-3.8-flash")

MIN_SECONDS_BETWEEN_CALLS = 0.6
_last_call_at = 0.0

stats = {"calls": 0, "cached": 0, "retries": 0, "input_tokens": 0, "output_tokens": 0}

# ----------------------------------------------------------------------
# RESPONSE CACHE
#
# The free tier allows only 20 requests per day PER MODEL. Without a cache,
# re-running an eval to fix a formatting bug would cost a full day's quota.
#
# We hash everything that affects the answer (model, prompt, system,
# temperature, seed, max_tokens) into a filename. Same inputs -> same file
# -> zero API calls. Delete the .cache folder to force fresh answers.
# ----------------------------------------------------------------------
CACHE_DIR = pathlib.Path(__file__).parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)


def _cache_key(model, prompt, system, temperature, max_tokens, seed) -> str:
    payload = json.dumps(
        [model, prompt, system, temperature, max_tokens, seed], sort_keys=True
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


# ----------------------------------------------------------------------
# WHICH ERRORS ARE WORTH RETRYING
#
# Retry  = the same request might succeed if we just wait.
#   429 RESOURCE_EXHAUSTED  we called too fast
#   503 UNAVAILABLE         Google's servers are busy right now
#   500 / 502 / 504         transient server-side failures
#
# Do NOT retry = the request itself is wrong; waiting changes nothing.
#   400 INVALID_ARGUMENT    we sent a bad parameter
#   401 / 403               bad or unauthorised key
#   404 NOT_FOUND           model does not exist
#
# Retrying a 400 four times just burns four requests to fail four times.
# ----------------------------------------------------------------------
RETRYABLE = (
    "429", "RESOURCE_EXHAUSTED",
    "500", "INTERNAL",
    "502",
    "503", "UNAVAILABLE",
    "504", "DEADLINE_EXCEEDED",
)


def _is_retryable(error: Exception) -> bool:
    message = str(error)
    return any(marker in message for marker in RETRYABLE)


def ask(
    prompt: str,
    temperature: float = 0.0,
    system: str | None = None,
    max_tokens: int | None = None,
    seed: int | None = None,
    top_p: float | None = None,
    top_k: int | None = None,
    use_cache: bool = True,
    model: str | None = None,
    max_retries: int = 6,
) -> str:
    """
    Send one prompt to the model and return its text.

    temperature : 0.0 = pick the most likely token. Higher = more varied.
    system      : optional instruction framing the model's role.
    max_tokens  : cap on output length. Careful - hidden 'thinking' tokens
                  count against this too, so a low value can return "".
    seed        : fixes the random draw. temperature=0 alone is NOT enough
                  for identical output on a thinking model.
    use_cache   : reuse a saved answer for identical inputs. On by default -
                  free tier is per-day per-model. Pass False when you
                  deliberately want fresh variation.
    top_p       : nucleus sampling. Keep only the likeliest tokens whose
                  probabilities sum to this, then sample from them.
    top_k       : keep only the k likeliest tokens, then sample.
    model       : override the default model for this one call. Week 6 uses
                  this to send judging to a stronger model.
    """
    global _last_call_at

    active_model = model or MODEL

    key = _cache_key(active_model, prompt, system, temperature, max_tokens,
                     (seed, top_p, top_k))
    cache_file = CACHE_DIR / f"{key}.json"
    if use_cache and cache_file.exists():
        stats["cached"] += 1
        return json.loads(cache_file.read_text(encoding="utf-8"))["response"]

    settings = {
        "temperature": temperature,
        # This model REJECTS thinking_budget=0 - thinking cannot be fully
        # switched off, only turned down. 'low' is the cheapest it accepts.
        "thinking_config": types.ThinkingConfig(thinking_level="low"),
    }
    if system is not None:
        settings["system_instruction"] = system
    if max_tokens is not None:
        settings["max_output_tokens"] = max_tokens
    if seed is not None:
        settings["seed"] = seed
    if top_p is not None:
        settings["top_p"] = top_p
    if top_k is not None:
        settings["top_k"] = top_k

    config = types.GenerateContentConfig(**settings)

    delay = 2.0
    for attempt in range(max_retries):
        gap = time.time() - _last_call_at
        if gap < MIN_SECONDS_BETWEEN_CALLS:
            time.sleep(MIN_SECONDS_BETWEEN_CALLS - gap)

        try:
            response = _client.models.generate_content(
                model=active_model, contents=prompt, config=config
            )
            _last_call_at = time.time()

            stats["calls"] += 1
            usage = getattr(response, "usage_metadata", None)
            if usage:
                stats["input_tokens"] += getattr(usage, "prompt_token_count", 0) or 0
                stats["output_tokens"] += getattr(usage, "candidates_token_count", 0) or 0

            text = (response.text or "").strip()

            if use_cache:
                cache_file.write_text(
                    json.dumps({"prompt": prompt, "response": text}, indent=1),
                    encoding="utf-8",
                )

            return text

        except Exception as error:
            _last_call_at = time.time()

            if not _is_retryable(error):
                raise

            if attempt == max_retries - 1:
                # Out of retries. If it was a rate limit, say something useful
                # instead of dumping a stack trace.
                if "429" in str(error) or "RESOURCE_EXHAUSTED" in str(error):
                    raise SystemExit(
                        "\nRate limited on every attempt - your free quota for "
                        f"{active_model} looks spent.\n"
                        "Run:  python week1/00_quota.py   to see which models "
                        "still work, then set GEMINI_MODEL in .env.\n"
                        "Daily free quota resets at midnight US Pacific "
                        "(~12:30 PM IST).\n"
                    )
                raise

            stats["retries"] += 1
            # Print enough of the error to be diagnosable. A truncated 429
            # hides WHICH quota you hit, which is the only useful part.
            label = " ".join(str(error).split())[:200]
            print(f"    [retryable error, waiting {delay:.0f}s] {label}")
            time.sleep(delay)
            delay *= 2          # 2s, 4s, 8s, 16s, 32s

    raise RuntimeError("unreachable")


def print_stats() -> None:
    """Report what this run cost. Useful evidence for your mentor review."""
    print(
        f"\n[{MODEL}]  api_calls={stats['calls']}  from_cache={stats['cached']}  "
        f"retries={stats['retries']}  in={stats['input_tokens']} tok  "
        f"out={stats['output_tokens']} tok"
    )
