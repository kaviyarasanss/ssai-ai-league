"""
DEBUGGING BY BISECTION.

The API said only: 400 INVALID_ARGUMENT "Request contains an invalid argument."
It did not say WHICH argument. So we send the request repeatedly, adding one
argument at a time, and watch for the first one that breaks.

This is the same technique you'd use on a failing payment gateway call.

Run:  python week1/00_diagnose.py
"""
import os
import warnings
from dotenv import load_dotenv
from google import genai
from google.genai import types

warnings.filterwarnings("ignore")
load_dotenv()

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL = os.environ.get("GEMINI_MODEL", "models/gemini-3.6-flash")
PROMPT = "Say the word: ok"

print(f"Model: {MODEL}\n")

# Each entry: (label, config-or-None). We go from simplest to most complex.
attempts = [
    ("no config at all",
     None),

    ("temperature only",
     types.GenerateContentConfig(temperature=0.0)),

    ("temperature + max_output_tokens",
     types.GenerateContentConfig(temperature=0.0, max_output_tokens=80)),

    ("+ thinking_budget=0",
     types.GenerateContentConfig(temperature=0.0, max_output_tokens=80,
                                 thinking_config=types.ThinkingConfig(thinking_budget=0))),

    ("+ thinking_budget=128",
     types.GenerateContentConfig(temperature=0.0, max_output_tokens=80,
                                 thinking_config=types.ThinkingConfig(thinking_budget=128))),

    ("+ thinking_level='low'",
     types.GenerateContentConfig(temperature=0.0, max_output_tokens=80,
                                 thinking_config=types.ThinkingConfig(thinking_level="low"))),

    ("temperature=1.8 (high temp allowed?)",
     types.GenerateContentConfig(temperature=1.8, max_output_tokens=80)),
]

for label, config in attempts:
    try:
        kwargs = {"model": MODEL, "contents": PROMPT}
        if config is not None:
            kwargs["config"] = config
        r = client.models.generate_content(**kwargs)
        text = (r.text or "[EMPTY TEXT]").strip().replace("\n", " ")
        print(f"  PASS  {label:<40} -> {text[:50]!r}")
    except Exception as e:
        msg = str(e).replace("\n", " ")
        print(f"  FAIL  {label:<40} -> {msg[:110]}")

print("\nThe first FAIL is the argument this model rejects.")
