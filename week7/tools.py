"""
WEEK 7 - The tools the agent can use.

TOOL DESIGN is the part people underrate. The model chooses a tool by reading
its DESCRIPTION and nothing else. A vague description is the number one cause
of an agent picking the wrong tool. Each description below says:
  what it does · when to use it · when NOT to use it

We give it exactly two tools, and they are deliberately complementary - the
same dense/keyword split measured in weeks 1 and 4:

  search_docs        semantic search. Good at "how do I stop fake webhooks".
                     Measured weakness: ERR-4032 vs ERR-4033 embed at 0.970,
                     so it cannot reliably tell error codes apart.

  lookup_error_code  exact keyword lookup via BM25. Good at ERR-4092, which
                     dense search ranked 28th of 47. Useless for prose questions.

This second tool is the structural fix week 5 identified as problem P3 and
week 6 proved reranking could not reach.
"""
import re
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from week3 import rag
from week4 import retrieval

_CHUNKS = None
_MATRIX = None
_BM25 = None


def init():
    """Build the index once. Shared by the agent and the workflow, so the
    race compares the two control flows, not two different indexes."""
    global _CHUNKS, _MATRIX, _BM25
    if _CHUNKS is None:
        _CHUNKS = rag.build_chunks(chunk_size=600, overlap=100)
        _MATRIX = rag.embed_chunks(_CHUNKS)
        _BM25 = retrieval.build_bm25(_CHUNKS)
    return len(_CHUNKS)


def search_docs(query: str, k: int = 3) -> str:
    """Semantic search over the SDK documentation."""
    init()
    hits = retrieval.rerank(query, rag.search(query, _CHUNKS, _MATRIX, k=12), k=k)
    return "\n\n".join(
        f"[{h['doc_id']} > {h['section']}]\n{h['text']}" for h in hits
    ) or "(nothing found)"


def lookup_error_code(code: str) -> str:
    """Exact lookup of an ERR-#### code by keyword search."""
    init()
    code = code.strip().upper()
    if not re.fullmatch(r"ERR-\d{3,4}", code):
        return (f"'{code}' is not a valid error code. Expected the form "
                f"ERR-4032. Use search_docs for prose questions.")
    hits = retrieval.bm25_search(code, _CHUNKS, _BM25, k=3)
    # Keep only chunks that literally contain the code - that is the whole
    # point of this tool. A near-miss here is exactly the P3 failure.
    exact = [h for h in hits if code in h["text"]]
    if not exact:
        return f"{code} is not mentioned anywhere in the documentation."
    return "\n\n".join(
        f"[{h['doc_id']} > {h['section']}]\n{h['text']}" for h in exact
    )


# The registry the agent is shown. Description text matters more than the code.
TOOLS = {
    "search_docs": {
        "fn": search_docs,
        "description": (
            "Semantic search over the PhoenixPay SDK documentation. "
            "USE FOR: questions phrased in words - policies, procedures, "
            "'how do I...', 'what happens if...'. "
            "DO NOT USE FOR: looking up a specific ERR-#### code; it confuses "
            "similar codes. Input: a search phrase."
        ),
    },
    "lookup_error_code": {
        "fn": lookup_error_code,
        "description": (
            "Exact lookup of one ERR-#### error code. "
            "USE FOR: finding what a specific code means, whether it is "
            "retryable, or whether it cascades. "
            "DO NOT USE FOR: general questions with no code in them. "
            "Input: exactly one code, e.g. ERR-4033."
        ),
    },
}


def run_tool(name: str, tool_input: str) -> str:
    if name not in TOOLS:
        return (f"No tool named '{name}'. Available: {', '.join(TOOLS)}.")
    try:
        return TOOLS[name]["fn"](tool_input)
    except Exception as e:
        return f"Tool error: {e}"


def tool_descriptions() -> str:
    return "\n".join(f"- {n}: {t['description']}" for n, t in TOOLS.items())
