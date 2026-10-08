# Week 10 — Multi-Agent & A2A

Track E: race the **docs squad** against the single agent.

---

## 1. The one idea

> "Multi-agent" is the most hyped idea in AI right now. Run the honest
> experiment: build a team, race it against one agent **on the same tests**,
> and keep whichever actually wins.

**Often the single agent wins. That is a result, not a failure.**

---

## 2. The pattern — orchestrator / worker

```
manager            reads the question, decides who does what
  ├─ specialist A    error codes only      (tool: lookup_error_code)
  └─ specialist B    policy and prose only (tool: search_docs)
manager            composes one answer from their reports
```

**Why specialists are narrow:** one tool, one job → a short unambiguous
prompt, and it *cannot* pick the wrong tool because there is only one. The
appeal isn't "more brains" — it's **less ambiguity each**.

---

## 3. The hidden cost — this is the week

**Every hand-off re-sends context.** There is no shared memory between
agents. Nothing is passed by reference; it is all re-typed into a new prompt.

| step | what gets sent |
|---|---|
| manager plan | the question |
| → specialist A | A's full instructions + its task |
| → specialist B | B's full instructions + its task |
| → manager compose | **both reports, again** ← biggest prompt in the run |

So a 3-agent team is **4–6 calls**, against the single agent's **2–3** with
one growing scratchpad.

---

## 4. Measuring tokens honestly

The trap: **a call served from the disk cache reports zero tokens.** If the
squad happened to hit more cached prompts, a naive count would show it using
*fewer* tokens — a lie about the exact thing we're measuring.

So `week10/meter.py` counts **two ways**:

| | what it is |
|---|---|
| **work** | estimated tokens the prompt + reply represent (~4 chars/token), cached or not |
| **billed** | what the API actually charged today — cache hits are 0 |

**The race is decided on `work`**, because that's the real size of the
conversation each design needs — what production pays on a cold cache.
`billed` is shown alongside so the saving is visible and nobody guesses which
number they're reading.

Cost = work tokens × the published rate, one constant in `meter.py`. If the
rate is wrong the *comparison* still holds; only the absolute dollars move.

---

## 5. The result

Same 4 questions, same facts, same tools, same index, same model, same
process, same meter. **Only the control flow differs.**

| | SINGLE | SQUAD | ratio |
|---|---|---|---|
| **quality** | 0.750 | 0.750 | — |
| speed | — | — | ran in sequence |
| **tokens (work)** | 8,641 | 11,618 | **1.34×** |
| **cost** | $0.001494 | $0.002447 | **1.64×** |
| LLM calls | 11 | 22 | **2.00×** |

**Verdict: keep the single agent.** Same quality, 1.64× the cost. The team
bought nothing and billed more for it.

Note cost rose *faster* than tokens (1.64× vs 1.34×) — the squad's extra
tokens are weighted toward **output**, which is priced 4× input.

---

## 6. When multi-agent *would* be worth it

- The parts are **genuinely independent and run in parallel**, so extra
  tokens buy wall-clock time back. *(Ours ran in sequence — no time bought.)*
- Sub-jobs need **clearly different instructions**, long enough that one
  prompt holding all of them would confuse the model.
- A specialist needs **different permissions** — one that can write, one
  read-only. (Week 8's least privilege.)
- Sub-jobs want **different models** — a cheap one for the easy half.

**When it isn't:**

- A short pipeline you could write down in advance → that's Week 7's lesson
- Sub-tasks that depend on each other → they serialise anyway
- Anything where one agent already passes the tests

---

## 7. A2A — agent to agent

| | connects | |
|---|---|---|
| **MCP** (week 9) | an agent → **tools and data** | "what can you do?" |
| **A2A** (week 10) | an agent → **other agents** | "can you take this task?" |

They're complementary, not competitors. An agent can use MCP for its tools
*and* A2A to delegate to a peer.

**AgentCard** — the A2A equivalent of `tools/list`: a published description
of what an agent *is* — its name, skills, endpoint, and auth. One agent reads
another's card to decide whether to hand work over. Same principle as Week 7
and Week 9: **the description is the interface.**

**Task lifecycle** — A2A work is a *task* with states, not one request/reply:
`submitted → working → (input-required) → completed / failed / canceled`.
That matters because another agent's job may take minutes, may need to come
back and ask a question, and may be cancelled. MCP's `tools/call` is a single
round trip; A2A assumes long-running, interruptible work.

**Our squad is not A2A** — it's in-process function calls. A2A is what you'd
use if specialist B belonged to another team or ran on another server. Worth
saying plainly rather than overclaiming.

**CrewAI / AutoGen** — frameworks that give you the manager/specialist
pattern out of the box (roles, hand-offs, shared memory). Same trade as
LangGraph in Week 7: they'd have hidden the thing being measured here. Once
you've paid for the hand-offs by hand, you know what the framework is
spending on your behalf.

---

## 8. Likely evaluator questions

**Isn't a team always better?** Usually not. Every hand-off re-sends
everything, so a team can cost several times more for the same or worse
result. I measured it: same quality, 1.64× cost, so I kept the single agent.

**Why did it cost more?** Not a guess — the mechanism. No shared memory
between agents; the compose call re-sends both reports.

**When would you use one?** Truly parallel independent parts, clearly
different instructions, different permissions, or different models per
sub-job.

**MCP vs A2A?** MCP connects an agent to tools. A2A connects an agent to
other agents.

**Is your squad A2A?** No — in-process calls. A2A is for crossing a process
or team boundary.

**How did you keep the race fair?** Same questions, facts, tools, index,
model, process and meter. Only the control flow differs.

---

## Run it

```
python week10/race.py          both, on the same 4 questions  (~20 requests)
python week10/race.py --fresh  ignore the checkpoint and redo
```
