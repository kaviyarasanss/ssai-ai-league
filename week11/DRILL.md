# The Support Drill — a runbook

A customer complaint is never a trace id. It is a sentence like *"it gave
us bad code a while back"*. This is the procedure for turning one into the
other, written so somebody who is not me can follow it at 2am.

`RESULTS.md` section 2 shows one completed run of this drill. This file is
the reusable procedure.

---

## The rule

**Never start by reading the log. Start by turning the complaint into
filters.** A 450-line log takes twenty minutes to read and a human will
miss the line anyway. Three filters take about ten seconds.

---

## Step 1 — translate the complaint into filters

Every phrase a person actually says maps to a flag:

| what they say | filter |
|---|---|
| "something about webhooks" | `--text webhook` |
| "a couple of weeks ago" | `--since 21d` |
| "the code doesn't work any more" | `--deprecated` |
| "it was quoting the refunds page" | `--doc 08_refunds.md` |
| "it just hung" | `--slowest 10` |
| "our bill spiked that day" | `--costliest 10` |
| "here's the id from the ticket" | `--id tr_…` |

Combine them. One filter is almost never enough:

```
python week11/find.py --text webhook --since 45d --deprecated
```

**Order matters for speed, not for correctness.** Put the cheapest, most
selective filter first — usually `--text`.

---

## Step 2 — narrow to a handful

```
python week11/find.py --text webhook --since 45d
```

The table marks two things for you:

```
! = the answer contains a removed SDK method
~ = synthetic noise, not a real request
```

If `!` appears, you are almost certainly done — jump to step 3. If the list
is still long, add `--real-only` to drop the noise, then `--deprecated`.

**If nothing matches**, do not conclude it never happened. Check in this
order: widen the window (`--since 90d`), try the user's word rather than
yours (they said "callback", the docs say "webhook"), then search the
answer text rather than the question — `find.py` already searches both.

---

## Step 3 — open the one trace

```
python week11/find.py --id tr_9f21ab40c7d3
```

This is the whole request, and it answers the four questions support will
ask next:

1. **What was actually asked?** — the exact question, not the paraphrase in
   the ticket.
2. **What did it answer?** — the full text, with any removed SDK method
   flagged and its replacement named.
3. **Why did it answer that?** — the `docs:` line on each retrieval span
   names every document it read. A wrong answer is nearly always a
   retrieval story.
4. **What did it cost, and where?** — per-step ms and USD, plus the slowest
   and costliest step called out by name.

---

## Step 4 — decide which kind of wrong it is

This is the step people skip, and it decides the fix:

| what the trace shows | kind of failure | fix |
|---|---|---|
| it never called the tool that holds the fact | **skipped step** | week 8 required-step gate |
| it read the right doc, but the doc is now stale | **stale corpus** | update the doc **and** add an output validator |
| it read the wrong doc entirely | **retrieval miss** | fix the query or the index |
| the answer contradicts the doc it read | **generation error** | prompt, or model |

The drill in `RESULTS.md` is the second row, and it is the most common one
in a documentation assistant: *the answer was correct when it was given,
and the world changed underneath it.* No prompt tuning prevents that. Only
the log finds it.

---

## Step 5 — close the loop, or it will happen again

A fixed bug with no test is a bug you will ship twice.

1. Add the case to `CASES` in `week11/regress.py` — the question, the rule,
   and the trace id it came from.
2. Run `python week11/regress.py`. It should **FAIL**. If a new test passes
   immediately, it is testing nothing.
3. Apply the fix.
4. Re-run. It should pass — and the replay output will show the first
   logged answer failing and the latest passing, side by side.

Step 2 is not optional. A regression test that was never seen to fail is
not evidence of anything.

---

## Quick reference

```
python week11/find.py --stats                       health of the whole log
python week11/find.py --text <word> --since 30d     narrow by topic + time
python week11/find.py --deprecated --real-only      every known-bad answer
python week11/find.py --doc 07_webhooks.md          who read this document
python week11/find.py --slowest 10                  latency complaints
python week11/find.py --costliest 10                bill complaints
python week11/find.py --id tr_xxxxxxxxxxxx          the full request
python week11/find.py --text webhook --json         pipe to jq
```
