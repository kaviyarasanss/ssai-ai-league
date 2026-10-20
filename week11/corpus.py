"""
WEEK 11 - CORPUS VERSIONING.

WHY THIS FILE EXISTS
    Week 11 needs a documentation change to exist: a method that WAS the
    documented way to do something, and now is deprecated. Without one,
    "find the code sample that used a deprecated method" has nothing to
    find.

    The lazy way is to edit week3/docs/ in place. I am not doing that, for
    one hard reason:

        weeks 3, 4, 6, 7, 8 and 10 all published MEASURED numbers against
        the 10-document corpus. Editing it would change chunk counts and
        retrieval ranks, and every one of those results would quietly stop
        being reproducible.

    So the corpus is VERSIONED instead:

        v1  week3/docs/                   10 docs - what weeks 3-10 measured
        v2  week11/docs_v2/  (generated)  11 docs - v1 + the migration doc

    v2 is rebuilt from v1 every run, so v1 is the single source of truth
    and v2 can never drift from it by hand-editing.

THE REALISTIC STORY THIS MODELS
    v1 is production last month. The SDK 3.0 migration note did not exist
    yet, so the only documented way to verify a webhook was
    `Webhook.construct_event()`. Answers given then used it, correctly.

    v2 is production today. 11_sdk_migration.md now says construct_event is
    REMOVED in 3.0 and carries a security advisory.

    That gap is the whole week: an answer that was right when it was given,
    is wrong now, and the only way to find it is the log.
"""
import re
import sys
import shutil
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

V1 = ROOT / "week3" / "docs"
EXTRA = HERE / "docs_extra"
V2 = HERE / "docs_v2"

# The symbols a code sample must not contain any more. One list, used by
# the drill (to find offenders) and by the regression test (to keep them
# out). Two copies of this list would drift; one cannot.
DEPRECATED = {
    "construct_event": "Webhook.verify_and_parse",
    "Payment.charge": "Payment.create",
    "Refund.issue": "Refund.create",
}


def build_v2() -> pathlib.Path:
    """Rebuild docs_v2 from v1 + the extra docs. Never touches v1."""
    if V2.exists():
        shutil.rmtree(V2)
    V2.mkdir(parents=True)
    for src in sorted(V1.glob("*.md")):
        shutil.copy2(src, V2 / src.name)
    for src in sorted(EXTRA.glob("*.md")):
        shutil.copy2(src, V2 / src.name)
    return V2


def use(version: str = "v2") -> int:
    """
    Point week7's tools at a corpus version, WITHOUT editing week7.

    week7.tools.init() builds its index only `if _CHUNKS is None`. So if we
    fill those module globals first, init() becomes a no-op and the agent
    runs against whichever corpus we chose. No edit to week7/tools.py, so
    weeks 7-10 still behave exactly as they did when they were measured.

    Returns the number of chunks indexed.
    """
    from week3 import rag
    from week4 import retrieval
    from week7 import tools

    folder = V1 if version == "v1" else build_v2()
    chunks = rag.build_chunks(chunk_size=600, overlap=100, folder=folder)
    tools._CHUNKS = chunks
    tools._MATRIX = rag.embed_chunks(chunks)
    tools._BM25 = retrieval.build_bm25(chunks)
    return len(chunks)


def find_deprecated(text: str) -> list[str]:
    """Which deprecated symbols this answer actually USES.

    MEASURED BUG, AND THE FIX (week 12 integration testing)
        The first version matched the bare symbol name anywhere in the
        text. That made the guard reject its own repair: repair() asks the
        model to say "construct_event was removed in 3.0, use
        verify_and_parse" - which is the CORRECT answer - and then
        validate() saw the string "construct_event" and rejected it again.
        Live regression run R1: `repaired=True` followed immediately by
        `still bad after repair`. A validator that cannot pass its own fix
        is not a validator, it is a loop.

        So the detector now matches the CALL form only - the symbol
        followed by an open paren, optionally across a line break:

            phoenixpay.Webhook.construct_event(payload=...)   -> flagged
            "construct_event was removed in 3.0, use ..."     -> allowed

        That is the real rule anyway: the danger is code that CALLS a
        removed method. Prose that warns about it is the thing we want.
    """
    text = text or ""
    found = []
    for sym in DEPRECATED:
        # tail of the dotted name, e.g. "Payment.charge" -> "charge"
        leaf = re.escape(sym.split(".")[-1])
        if re.search(leaf + r"\s*\(", text):
            found.append(sym)
    return found


if __name__ == "__main__":
    print(f"v1: {len(list(V1.glob('*.md')))} docs  -> {V1}")
    p = build_v2()
    print(f"v2: {len(list(p.glob('*.md')))} docs  -> {p}")
    print(f"deprecated symbols tracked: {', '.join(DEPRECATED)}")
