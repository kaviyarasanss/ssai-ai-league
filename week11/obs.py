"""
WEEK 11 - OBSERVABILITY. The app watching itself.

THE ONE IDEA
    In production nobody is watching. If a request was not logged, it did
    not happen - and when a customer says "it gave me a wrong answer last
    Tuesday", a log is the only thing standing between you and a shrug.

WHAT THIS FILE IS
    A tracer. It records ONE LINE OF JSON PER REQUEST into
    week11/logs/traces.jsonl, and inside that line, one SPAN per step.

        trace   = one user request, start to finish
        span    = one step inside it (an LLM call, or a tool call)

    This is the same trace/span model LangSmith, Phoenix and OpenTelemetry
    use. I am writing it by hand rather than installing one of them for two
    reasons, and I will say both to the mentor:
      1. Writing it is the only way to understand what those tools record.
      2. Nothing here needs a network service, so the whole thing still
         runs offline and inside a free tier.
    The shape is deliberately OTel-ish (trace_id / span name / duration /
    attributes), so swapping in a real backend later is a mapping job,
    not a rewrite.

WHY A WRAPPER AND NOT EDITS TO week7/agent.py
    Weeks 8 and 10 published measured results produced by that exact file.
    If I instrument it by editing it, those results stop being reproducible
    and I would be quietly changing the thing I already reported on.
    So obs.py wraps llm.ask and tools.run_tool from the OUTSIDE. The agent
    is untouched and still runs un-instrumented for anyone who imports it
    directly. Same discipline as week 9's "adding a tool changed the agent
    by zero bytes".

WHAT EVERY SPAN CARRIES - and why each field is there
    name        what happened            ("llm.ask", "tool.search_docs")
    ms          how long it took         -> find the slow step, not the slow request
    tok_in/out  size of the step         -> find the expensive step
    usd         cost of THIS step        -> mentor check 2: per step, not one lump
    cached      served from disk cache   -> a 0-cost step is not a free step
    note        tool input / model name  -> enough to replay the step by hand

    The mentor check is explicitly "time and cost per step, not just one
    total". A single total tells you a request was slow. Spans tell you
    WHICH step was slow, which is the only version you can act on.
"""
import io
import os
import sys
import json
import time
import uuid
import pathlib
import datetime
import contextlib

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

LOG_DIR = HERE / "logs"
LOG_DIR.mkdir(exist_ok=True)
TRACES = LOG_DIR / "traces.jsonl"

# ----------------------------------------------------------------------
# Rates live in ONE place - week 10's meter. Importing them rather than
# re-declaring them means the cost column here and the cost column in
# week 10 can never silently disagree.
# ----------------------------------------------------------------------
from week10.meter import USD_PER_1M_INPUT, USD_PER_1M_OUTPUT, est   # noqa: E402


def usd(tok_in: int, tok_out: int) -> float:
    return (tok_in / 1_000_000) * USD_PER_1M_INPUT + \
           (tok_out / 1_000_000) * USD_PER_1M_OUTPUT


def new_trace_id() -> str:
    """Short, greppable, and unique enough for a day's traffic.

    A full uuid4 is unguessable but nobody can read one out over a support
    call. 12 hex chars is 48 bits - collision risk is negligible at this
    volume, and 'tr_9f21ab40c7d3' fits in a ticket."""
    return "tr_" + uuid.uuid4().hex[:12]


class Trace:
    """One user request. Collects spans, then writes itself as one JSON line."""

    def __init__(self, question: str, track: str = "E", meta: dict = None,
                 **extra_meta):
        self.id = new_trace_id()
        self.ts = datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds")
        self.question = question
        self.track = track
        # meta= as a dict and meta as keywords both work; keywords win.
        self.meta = {**(meta or {}), **extra_meta}
        self.spans: list[dict] = []
        self.answer = None
        self.stop_reason = None
        self.error = None
        self._t0 = time.time()

    # -- span recording ------------------------------------------------
    def add_span(self, name: str, ms: float, tok_in: int = 0, tok_out: int = 0,
                 cached: bool = False, note: str = "", **extra) -> None:
        self.spans.append({
            "i": len(self.spans) + 1,
            "name": name,
            "ms": round(ms, 1),
            "tok_in": tok_in,
            "tok_out": tok_out,
            "usd": round(usd(tok_in, tok_out), 8),
            "cached": cached,
            "note": note[:160],
            **extra,
        })

    def backdate(self) -> None:
        """Make the wall-clock total equal the sum of the spans.

        Only used by the synthetic noise generator, which writes 400 traces
        in a fraction of a second. Without this every synthetic trace would
        report 0 ms total while carrying spans worth seconds - and a
        latency column that disagrees with its own spans is worse than no
        latency column."""
        self._t0 = time.time() - sum(s["ms"] for s in self.spans) / 1000.0

    # -- totals --------------------------------------------------------
    def totals(self) -> dict:
        return {
            "ms": round((time.time() - self._t0) * 1000, 1),
            "spans": len(self.spans),
            "llm_calls": sum(1 for s in self.spans if s["name"] == "llm.ask"),
            "tool_calls": sum(1 for s in self.spans if s["name"].startswith("tool.")),
            "cache_hits": sum(1 for s in self.spans if s["cached"]),
            "tok_in": sum(s["tok_in"] for s in self.spans),
            "tok_out": sum(s["tok_out"] for s in self.spans),
            "usd": round(sum(s["usd"] for s in self.spans), 8),
        }

    def to_dict(self) -> dict:
        return {
            "trace_id": self.id,
            "ts": self.ts,
            "track": self.track,
            "question": self.question,
            "answer": self.answer,
            "stop_reason": self.stop_reason,
            "error": self.error,
            "meta": self.meta,
            "totals": self.totals(),
            "spans": self.spans,
        }

    def write(self) -> str:
        """Append one line. JSONL, not JSON, on purpose: appending to a JSON
        array means rewriting the file; appending a line is O(1) and
        survives a crash mid-write with at most one corrupt line."""
        with io.open(TRACES, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(self.to_dict(), ensure_ascii=False) + "\n")
        return self.id


# ----------------------------------------------------------------------
# INSTRUMENTATION
#
# We wrap two functions and only two, because between them they account
# for every cent and every second the app spends:
#     llm.ask          the model calls      (cost + most of the latency)
#     tools.run_tool   the retrieval calls  (the rest of the latency)
#
# Everything else in the agent is local string handling and rounds to zero.
# ----------------------------------------------------------------------
_CURRENT: Trace | None = None
_patched = False
_orig_ask = None
_orig_run_tool = None


def _stats() -> dict:
    import llm
    return getattr(llm, "stats", None) or {"calls": 0, "input_tokens": 0,
                                           "output_tokens": 0}


def _wrapped_ask(prompt, *a, **kw):
    import llm
    t0 = time.time()
    st = _stats()
    b_calls, b_in, b_out = st["calls"], st["input_tokens"], st["output_tokens"]

    text = _orig_ask(prompt, *a, **kw)

    ms = (time.time() - t0) * 1000
    st = _stats()
    cached = st["calls"] == b_calls
    d_in = st["input_tokens"] - b_in
    d_out = st["output_tokens"] - b_out

    # A cache hit bills ZERO tokens. Recording 0 would make a cached step
    # look free AND weightless, and the request would look cheaper than the
    # work it actually represents. So when billed is 0 we fall back to the
    # ~4-chars-per-token estimate and FLAG the span as cached. Week 10's
    # billed-vs-work distinction, applied per span.
    if cached or (d_in == 0 and d_out == 0):
        d_in = est(prompt) + est(kw.get("system") or "")
        d_out = est(text)

    if _CURRENT is not None:
        model = kw.get("model") or getattr(llm, "MODEL", "?")
        _CURRENT.add_span("llm.ask", ms, d_in, d_out, cached,
                          note=f"model={model} prompt={len(prompt)}c",
                          model=model)
    return text


def _wrapped_run_tool(name, tool_input):
    t0 = time.time()
    out = _orig_run_tool(name, tool_input)
    ms = (time.time() - t0) * 1000
    if _CURRENT is not None:
        # doc_ids are the single most useful attribute on a retrieval span:
        # the support drill is almost always "which document did it read?"
        doc_ids = sorted({ln.split(" > ")[0].lstrip("[")
                          for ln in (out or "").splitlines()
                          if ln.startswith("[")})
        _CURRENT.add_span(f"tool.{name}", ms, 0, 0, False,
                          note=f"input={tool_input!r} -> {len(out or '')}c",
                          tool_input=tool_input, doc_ids=doc_ids)
    return out


def instrument() -> None:
    """Monkey-patch llm.ask and tools.run_tool. Idempotent."""
    global _patched, _orig_ask, _orig_run_tool
    if _patched:
        return
    import llm
    from week7 import agent as agent_mod
    from week7 import tools as tools_mod

    _orig_ask = llm.ask
    _orig_run_tool = tools_mod.run_tool

    llm.ask = _wrapped_ask
    tools_mod.run_tool = _wrapped_run_tool
    # week7.agent did `from llm import ask` and `from week7.tools import
    # run_tool`, so it holds its OWN references. Patching the modules alone
    # would miss every call the agent makes. Rebind the names it actually
    # uses. (Found this the hard way: the first version logged zero spans.)
    if hasattr(agent_mod, "ask"):
        agent_mod.ask = _wrapped_ask
    if hasattr(agent_mod, "run_tool"):
        agent_mod.run_tool = _wrapped_run_tool
    _patched = True


def uninstrument() -> None:
    global _patched
    if not _patched:
        return
    import llm
    from week7 import agent as agent_mod
    from week7 import tools as tools_mod
    llm.ask = _orig_ask
    tools_mod.run_tool = _orig_run_tool
    if hasattr(agent_mod, "ask"):
        agent_mod.ask = _orig_ask
    if hasattr(agent_mod, "run_tool"):
        agent_mod.run_tool = _orig_run_tool
    _patched = False


@contextlib.contextmanager
def trace(question: str, track: str = "E", **meta):
    """
    with obs.trace("how do I verify a webhook?") as t:
        result = run_agent(...)
        t.answer = result["answer"]

    The trace is written even if the body raises - an unlogged crash is
    exactly the request support will ask you about.
    """
    global _CURRENT
    instrument()
    t = Trace(question, track, meta)
    prev, _CURRENT = _CURRENT, t
    try:
        yield t
    except BaseException as e:
        t.error = f"{type(e).__name__}: {e}"
        raise
    finally:
        _CURRENT = prev
        t.write()


# ----------------------------------------------------------------------
# READING THE LOG
# ----------------------------------------------------------------------
def load(path: pathlib.Path = TRACES) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in io.open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            # One bad line must not cost you the whole log. This is the
            # reason for JSONL in the first place.
            continue
    return rows
