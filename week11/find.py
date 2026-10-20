"""
WEEK 11 - THE SEARCH TOOL. "Find me that answer from last Tuesday."

THE POINT
    A log you cannot search is a log you do not have. Mentor check 1 is
    "can they find a specific past answer from the logs QUICKLY" - so the
    deliverable is not the log file, it is this: a tool that turns a vague
    complaint into one trace_id.

    Every filter here exists because it answers a sentence a real person
    actually says:

      "it was something about webhooks"          --text webhook
      "it was a couple of weeks ago"             --since 21d
      "it gave code that doesn't work any more"  --deprecated
      "it was reading the refunds page"          --doc 08_refunds.md
      "it took ages"                             --slowest 10
      "the bill spiked that day"                 --costliest 10
      "here's the trace id from the ticket"      --id tr_9f21ab40c7d3

    Filters COMBINE, because one filter is never enough on a real log:
        python week11/find.py --text webhook --since 45d --deprecated

USAGE
    python week11/find.py --stats
    python week11/find.py --text webhook --since 45d
    python week11/find.py --deprecated
    python week11/find.py --id tr_9f21ab40c7d3        full span breakdown
"""
import sys
import json
import pathlib
import argparse
import datetime

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from week11 import obs, corpus                                   # noqa: E402


def _age_days(row: dict) -> float:
    try:
        ts = datetime.datetime.fromisoformat(row["ts"])
    except Exception:
        return 1e9
    now = datetime.datetime.now(datetime.timezone.utc)
    return (now - ts).total_seconds() / 86400.0


def _parse_window(s: str | None) -> float | None:
    """'30d' -> 30.0, '12h' -> 0.5, '45' -> 45.0"""
    if not s:
        return None
    s = s.strip().lower()
    if s.endswith("d"):
        return float(s[:-1])
    if s.endswith("h"):
        return float(s[:-1]) / 24.0
    return float(s)


def filter_rows(rows: list[dict], args) -> list[dict]:
    out = rows

    if args.id:
        return [r for r in out if r["trace_id"] == args.id]

    if args.text:
        needle = args.text.lower()
        out = [r for r in out
               if needle in (r.get("question") or "").lower()
               or needle in (r.get("answer") or "").lower()]

    if args.deprecated:
        out = [r for r in out if corpus.find_deprecated(r.get("answer") or "")]

    win = _parse_window(args.since)
    if win is not None:
        out = [r for r in out if _age_days(r) <= win]

    if args.doc:
        out = [r for r in out
               if any(args.doc in (s.get("doc_ids") or []) for s in r["spans"])]

    if args.tool:
        want = f"tool.{args.tool}"
        out = [r for r in out if any(s["name"] == want for s in r["spans"])]

    if args.real_only:
        out = [r for r in out if not r["meta"].get("synthetic")]

    if args.slowest:
        out = sorted(out, key=lambda r: -r["totals"]["ms"])[:args.slowest]
    elif args.costliest:
        out = sorted(out, key=lambda r: -r["totals"]["usd"])[:args.costliest]
    else:
        out = sorted(out, key=lambda r: r["ts"], reverse=True)

    return out


def print_table(rows: list[dict], limit: int) -> None:
    if not rows:
        print("no matching traces")
        return
    print(f"\n{'trace_id':<18} {'when':<17} {'ms':>6} {'usd':>10}  question")
    print("-" * 96)
    for r in rows[:limit]:
        t = r["totals"]
        mark = "!" if corpus.find_deprecated(r.get("answer") or "") else " "
        syn = "~" if r["meta"].get("synthetic") else " "
        print(f"{mark}{syn}{r['trace_id']:<16} {r['ts'][:16]:<17} "
              f"{t['ms']:>6.0f} {t['usd']:>10.6f}  "
              f"{' '.join((r['question'] or '').split())[:44]}")
    if len(rows) > limit:
        print(f"... and {len(rows) - limit} more (use --limit)")
    print(f"\n{len(rows)} match(es)    "
          f"! = answer contains a deprecated symbol    ~ = synthetic noise")


def print_trace(r: dict) -> None:
    """The per-step view. THIS is mentor check 2: time and cost per step."""
    t = r["totals"]
    print("=" * 78)
    print(f"trace_id   {r['trace_id']}")
    print(f"when       {r['ts']}")
    print(f"track      {r['track']}      corpus: {r['meta'].get('corpus','-')}"
          f"      synthetic: {bool(r['meta'].get('synthetic'))}")
    print(f"question   {' '.join((r['question'] or '').split())}")
    print(f"stop       {r.get('stop_reason')}")
    if r.get("error"):
        print(f"error      {r['error']}")
    print("-" * 78)
    print(f"{'#':>2} {'step':<22} {'ms':>8} {'tok_in':>7} {'tok_out':>8} "
          f"{'usd':>10}  note")
    for s in r["spans"]:
        flag = " (cached)" if s["cached"] else ""
        print(f"{s['i']:>2} {s['name']:<22} {s['ms']:>8.1f} {s['tok_in']:>7} "
              f"{s['tok_out']:>8} {s['usd']:>10.6f}  {s['note'][:34]}{flag}")
        if s.get("doc_ids"):
            print(f"{'':>2} {'':<22} {'':>8} {'':>7} {'':>8} {'':>10}  "
                  f"docs: {', '.join(s['doc_ids'])}")
    print("-" * 78)
    print(f"{'':>2} {'TOTAL':<22} {t['ms']:>8.1f} {t['tok_in']:>7} "
          f"{t['tok_out']:>8} {t['usd']:>10.6f}")
    # The slowest step, named. A total of 20s tells you nothing; "step 3,
    # tool.search_docs, 14.2s" tells you what to fix.
    if r["spans"]:
        slow = max(r["spans"], key=lambda s: s["ms"])
        dear = max(r["spans"], key=lambda s: s["usd"])
        print(f"\n   slowest step:   #{slow['i']} {slow['name']} "
              f"({slow['ms']:.0f}ms = {slow['ms']/max(t['ms'],1)*100:.0f}% of total)")
        print(f"   costliest step: #{dear['i']} {dear['name']} "
              f"(${dear['usd']:.6f} = {dear['usd']/max(t['usd'],1e-12)*100:.0f}% of total)")
    print("-" * 78)
    print("ANSWER:")
    print((r.get("answer") or "(none)")[:1500])
    flagged = corpus.find_deprecated(r.get("answer") or "")
    if flagged:
        print(f"\n   ** DEPRECATED SYMBOL IN ANSWER: {', '.join(flagged)}")
        for sym in flagged:
            print(f"      {sym}  ->  use {corpus.DEPRECATED[sym]} instead")
    print("=" * 78)


def print_stats(rows: list[dict]) -> None:
    real = [r for r in rows if not r["meta"].get("synthetic")]
    if not rows:
        print("log is empty - run: python week11/run_logged.py")
        return
    tot_usd = sum(r["totals"]["usd"] for r in rows)
    tot_ms = sum(r["totals"]["ms"] for r in rows)
    calls = sum(r["totals"]["llm_calls"] for r in rows)
    hits = sum(r["totals"]["cache_hits"] for r in rows)
    bad = [r for r in rows if corpus.find_deprecated(r.get("answer") or "")]
    oldest = min(rows, key=lambda r: r["ts"])["ts"][:10]
    newest = max(rows, key=lambda r: r["ts"])["ts"][:10]

    print(f"\ntraces           {len(rows)}  ({len(real)} real, "
          f"{len(rows)-len(real)} synthetic)")
    print(f"window           {oldest} .. {newest}")
    print(f"llm calls        {calls}   cache hits {hits} "
          f"({hits/max(calls,1)*100:.0f}%)")
    print(f"cost total       ${tot_usd:.6f}")
    print(f"cost per request ${tot_usd/len(rows):.6f}")
    print(f"mean latency     {tot_ms/len(rows):.0f} ms")
    print(f"p95 latency      "
          f"{sorted(r['totals']['ms'] for r in rows)[int(len(rows)*0.95)-1]:.0f} ms")
    print(f"deprecated hits  {len(bad)}   "
          f"{'<- ' + ', '.join(r['trace_id'] for r in bad[:4]) if bad else ''}")


def main() -> None:
    ap = argparse.ArgumentParser(description="search the request log")
    ap.add_argument("--id")
    ap.add_argument("--text")
    ap.add_argument("--since", help="30d, 12h, or a number of days")
    ap.add_argument("--doc", help="only traces that read this document")
    ap.add_argument("--tool", help="only traces that called this tool")
    ap.add_argument("--deprecated", action="store_true",
                    help="only answers containing a deprecated symbol")
    ap.add_argument("--real-only", action="store_true")
    ap.add_argument("--slowest", type=int)
    ap.add_argument("--costliest", type=int)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rows = obs.load()
    if args.stats:
        print_stats(rows)
        return

    hits = filter_rows(rows, args)

    if args.json:
        print(json.dumps(hits, indent=1)[:20000])
        return

    if args.id:
        if not hits:
            print(f"no trace with id {args.id}")
            return
        print_trace(hits[0])
        return

    print_table(hits, args.limit)


if __name__ == "__main__":
    main()
