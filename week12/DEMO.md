# The four-part demo — presenter's script

Target: **8 minutes**, leaving time for questions.
`python app.py --demo` runs parts 1–3 live. This is what to *say* while it
runs, and what to say when they push back.

> **Rehearse with `python app.py --demo --dry` first.** It prints the whole
> script and the real numbers without spending a single request, so you can
> practise as often as you like and still have quota left for the day.

---

## Before you start

```bash
python app.py --check
```

Do this **in front of them**. It takes a few seconds, it proves the thing
runs on the machine in the room, and if something is broken you find out
before the demo rather than during it.

Have a second terminal open and ready.

---

## Part 1 — a real run (≈2 min)

```bash
python app.py "A payment failed with ERR-4033. Should I retry the same card, and will it cascade to another acquirer?"
```

**Say while it runs:**

> One question, the full path. It retrieves from two indexes, reasons
> about which tool it needs, checks its own answer before showing it, and
> logs every step.

**Then point at the footer, not the answer.** The answer is the boring
part. Point at:

- `tools` — which tools it chose, and that *it* chose them
- `gated` — if non-zero, the agent tried to answer early and was refused
- `steps`, `time`, `cost` — per request, not per month
- `trace_id` — and then actually use it:

```bash
python week11/find.py --id tr_xxxxxxxxxxxx
```

> Every request is logged like this. Time and cost **per step**, and the
> documents it read. That last line is what you need when somebody says
> "it gave us a wrong answer last Tuesday."

---

## Part 2 — a real failure, and the fix (≈3 min)

**This is the part that counts.** The brief says a flawless demo counts
against you, and it is right: a demo where nothing fails is hiding
something.

`--demo` runs the same question twice — gate **off**, then gate **on**.

**Say:**

> This isn't a story about a bug. I'm going to turn the fix off and show
> you the bug.
>
> Week 8's trajectory audit found my top failure mode: the agent looks up
> the error code, finds a confident-looking chunk, and answers — without
> ever searching the policy, which lives in a *different document*. The
> answer looks fine. It's just missing the thing you asked about.
>
> I called it SKIPPED_STEP. In week 10's live race it happened on two of
> four questions.

Let it run with the gate off. **Read the answer out loud and let them
notice the gap themselves** — it will not mention cascading.

Then the gate-on run:

> The fix is a required-step gate. When the question has an error code in
> it, the answer isn't accepted until the agent has looked the code up
> *and* searched the policy. It rejects the early answer, tells the agent
> what it skipped, and lets it continue. Bounded at two pushes, so the
> gate can't cause a loop itself.

The comparison block prints both runs and the price of the fix.

> It costs about one extra call. That's the trade, and I'd rather state it
> than hide it.

**If the gate-off run happens to produce a correct answer** — say so
immediately, do not pretend:

> That's actually the more interesting case. Week 8 measured an
> outcome-versus-trajectory gap of +0.250 — a run that was *right by
> luck*, on a path that skipped a required step. Grading the answer alone
> would have scored that a pass. That's exactly why I grade the path.

---

## Part 3 — a number that improved (≈2 min)

Printed from the result files on disk — **not typed into a slide**.

Lead with the one you can defend hardest:

| | before | after |
|---|---|---|
| trajectory pass rate (week 8) | 0.250 | **1.000** |
| `SKIPPED_STEP` failures | 3 | **0** |
| cost | — | **+6 LLM calls** |

> The number I'd defend hardest is the trajectory one, because it's the
> one that reflects whether the *reasoning* was sound, not whether it got
> lucky. And I'm quoting the cost in the same breath: the fix isn't free,
> it's +6 calls across four questions.

Then week 10 and week 11's cost figures, both of which `--demo` prints.

**On the week 11 cache number, volunteer the caveat before anyone asks:**

> That halving is on a workload I built to contain paraphrases. On my
> actual logged traffic the near-duplicate rate is much lower — and most
> repeats are byte-identical, which the hash cache has handled for free
> since week 1. Both numbers are in the write-up. Quoting only the first
> would be misleading.

---

## Part 4 — what's next (≈1 min)

Four items, in `app.py --demo` output. Say them as *scoped work*, not
regrets:

1. Run the week 10 specialists **in parallel** — the one axis where a
   squad could genuinely beat one agent. Untested, so not claimed.
2. Generate the deprecated-symbol list from the SDK changelog — right now
   it depends on me updating a dict by hand.
3. Log rotation and retention — prompts contain user text.
4. Test retrieval beyond 10 documents.

---

## Defending the numbers

**"How do you know the gate helped?"**
> One variable. Same questions, same tools, same index, same model, same
> process, same meter — only `require_tools` changes. `week8/measure.py`
> runs both sides.

**"Isn't 4 questions too few?"**
> Yes, and I say so in the write-up. It's a real signal, not a statistic.
> No repeats, no variance estimates. The free tier is 20 requests a day
> per model and that shaped the whole project.

**"What does it cost to run?"**
> Per request, from the log: cost per request, mean and p95 latency,
> and which step the money goes to. `python week11/find.py --stats`.
> Nearly all of it is the model calls, almost none is retrieval — which
> is why I cached the model call and not the search.

**"What happens when it's wrong?"**
> Three layers. The gate stops it answering without looking. The
> validator stops it shipping a removed SDK method. And if something gets
> through anyway, the log lets me find it from a vague complaint — I
> practised exactly that in week 11's drill.

**"Why not use GPT-4 / a bigger model?"**
> Free tier, and it's the honest constraint. But the failures I measured
> weren't knowledge failures — they were *trajectory* failures, the agent
> not looking something up. A bigger model doesn't fix not looking.

**"Why not multi-agent?"**
> I built it and measured it. The squad won on quality, 4/4 versus 2/4,
> but cost 2.44× the calls and 4.57× the wall-clock. Its whole advantage
> was forcing a second lookup — which week 8's gate buys for about +1 call
> instead of +13. So I shipped the single agent with the gate.

**"What's the weakest part?"**
> That the documentation can go stale underneath a correct answer. That's
> the failure I caught in week 11, and the validator's symbol list is
> maintained by hand — it should come from the SDK changelog.
> `week12/WEAKSPOTS.md` has all nine, with evidence.

**"Did you write all this yourself?"**
> I used AI assistance throughout, which is the point of the programme.
> What I can do is explain any line of it, tell you why each piece is
> there, and name the measurement that justified it.

---

## Rules for the room

1. **Never quote a number you cannot point at a file for.** If it isn't
   in a results file, say "I haven't measured that."
2. **Volunteer the caveat before they find it.** A limitation you raise is
   rigour; one they find is a gap.
3. **"I don't know" is a complete answer** — followed by what you would
   measure to find out.
4. **Don't let the demo run silently.** Narrate while it works.
5. **If something breaks live, debug it in front of them.** You have a log
   designed for exactly that. It is the best possible accident.
