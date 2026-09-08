"""
QUOTA DIAGNOSTIC.

A 429 says "you exceeded your quota" but the useful part - WHICH quota, and
what the limit is - is buried in the error body. This prints it in full.

Then it tries one call against several models, so we can see which ones your
free tier actually allows.

Costs at most 1 request per model. Run:  python week1/00_quota.py
"""
import os
import json
import logging
import warnings

from dotenv import load_dotenv
from google import genai
from google.genai import types

warnings.filterwarnings("ignore")
logging.getLogger("google_genai").setLevel(logging.ERROR)
logging.getLogger("google_genai.models").setLevel(logging.ERROR)
load_dotenv()

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

CANDIDATES = [
    "models/gemini-3.6-flash",        # what we pinned
    "models/gemini-3.8-flash",        # newest
    "models/gemini-3.5-flash",
    "models/gemini-3.5-flash-lite",
    "models/gemini-3.1-flash-lite",
    "models/gemini-2.5-flash-lite",
    "models/gemini-flash-lite-latest",
]

config = types.GenerateContentConfig(
    temperature=0.0,
    thinking_config=types.ThinkingConfig(thinking_level="low"),
)

print("Trying one call per model. This tells us what your free tier allows.\n")

working = []
for name in CANDIDATES:
    try:
        r = client.models.generate_content(
            model=name, contents="Reply with exactly: ok", config=config
        )
        text = (r.text or "").strip()[:30]
        print(f"  WORKS   {name:<36} -> {text!r}")
        working.append(name)
    except Exception as error:
        body = str(error)
        short = "429 quota" if "429" in body else body[:40].replace("\n", " ")
        print(f"  BLOCKED {name:<36} -> {short}")

        # Dig out the quota details - this is the bit that actually helps.
        details = getattr(error, "details", None)
        if details and "429" in body:
            blob = json.dumps(details, indent=1)
            noise = '{}"[] '
            for line in blob.splitlines():
                if any(k in line for k in ("quotaId", "quotaMetric", "quotaValue",
                                           "retryDelay", "limit", "model")):
                    print("            " + line.strip().strip(noise))

print("\n" + "=" * 60)
if working:
    print("Use one of the WORKS models. Set it in .env as GEMINI_MODEL=<name>")
    print(f"Suggested: {working[0]}")
else:
    print("Everything is throttled. Your daily free quota is spent.")
    print("It resets at midnight US Pacific time (about 12:30 PM IST).")
