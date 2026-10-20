# PhoenixPay SDK Docs Answer Engine

Ask questions about the PhoenixPay SDK documentation in plain English and
get an answer that cites the documents it came from — with the agent's
reasoning, cost and timing logged for every single request.

Built over twelve weeks of the AI Engineering League, Track E (developer
documentation). The week-by-week build is below; **this top section is all
you need to run it.**

---

## Quickstart

You need **Python 3.10 or newer** and a free Google AI Studio API key
(<https://aistudio.google.com> — no card required).

```bash
# 1. get the code
git clone https://github.com/kaviyarasanss/ssai-ai-league.git
cd ssai-ai-league

# 2. isolate the dependencies
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # Windows PowerShell
# source .venv/bin/activate       # macOS / Linux

# 3. install
pip install -r requirements.txt

# 4. add your key
copy .env.example .env            # Windows   (cp on macOS/Linux)
#   then open .env and paste:  GEMINI_API_KEY=your_key_here

# 5. check the machine is ready  <-- DO THIS BEFORE ANYTHING ELSE
python app.py --check
```

`--check` verifies the Python version, every package, your key, the
documentation corpus, and then builds the search index. **Every line it
prints that says FAIL also tells you the command that fixes it.** If it
ends with `READY.` you are done setting up.

> The first run downloads a ~90 MB embedding model. That is a one-off; it
> is cached afterwards and start-up drops to a few seconds.

### Ask it something

```bash
python app.py "what does ERR-4092 mean on a refund?"
python app.py "how do I verify a webhook signature?"
python app.py "which errors are safe to retry?"
python app.py --repl              # ask repeatedly
```

You get the answer, plus which tools it used, how many steps it took, what
it cost, and a `trace_id` for looking the request up later.

---

## What the other commands do

| command | what it does | API cost |
|---|---|---|
| `python app.py --check` | preflight — run this first | none |
| `python app.py "question"` | answer one question | ~2–4 requests |
| `python app.py --repl` | interactive | ~2–4 per question |
| `python app.py --eval` | the full test suite | none |
| `python app.py --demo` | the four-part demo | ~9 requests |
| `python app.py --demo --dry` | the demo script without spending quota | none |
| `python week11/find.py --stats` | health of the request log | none |
| `python week11/find.py --id tr_…` | one request, step by step | none |

**Free-tier quota is 20 requests per day, per model.** Answers are cached
on disk, so asking the same question twice costs nothing. If you see
`429 RESOURCE_EXHAUSTED`, that is the daily cap; it resets at midnight US
Pacific (~12:30 PM IST).

---

## How it works

One question travels through this path. Each stage came from a different
week, and each one is there because something measurably failed without it.

```
      your question
            |
   [1] RETRIEVE      two indexes, not one
            |          dense vectors (meaning) + BM25 (exact codes)
            |          because ERR-4032 and ERR-4033 embed at 0.970
            |          similarity — meaning-search cannot tell them apart
            |
   [2] REASON        a ReAct agent: THOUGHT -> ACTION -> OBSERVATION
            |          it picks the tool; four stop conditions stop it
            |          running away (steps, time, calls, repeat guard)
            |
   [3] GATE          refuse a final answer that skipped a required lookup
            |          week 8 found this was the single top failure mode
            |
   [4] VALIDATE      refuse an answer using an SDK method that was removed
            |          — then repair it against the migration notes
            |
   [5] LOG           write a trace: every step, its time, its cost,
            |          and which documents it read
            |
       the answer
```

**Why stages 3 and 4 both exist** — they look similar and are not
interchangeable. The gate fires *before* an answer exists and catches "the
agent never looked it up". The validator fires *after* and catches "the
agent read a page that is now out of date". Neither can do the other's job.

---

## Finding a past answer

Every request is logged. When somebody says *"it gave us bad code a while
back"*, you do not read the log — you filter it:

```bash
python week11/find.py --text webhook --since 45d    # topic + time
python week11/find.py --deprecated                  # answers using a removed method
python week11/find.py --id tr_9f21ab40c7d3          # the whole request
python week11/find.py --slowest 10                  # latency complaints
python week11/find.py --costliest 10                # billing complaints
```

The full procedure is in [`week11/DRILL.md`](week11/DRILL.md).

---

## Known weak spots

I would rather tell you than have you find out.
See [`week12/WEAKSPOTS.md`](week12/WEAKSPOTS.md) for the full list with
evidence. The short version:

- **It answers from the documents it is given.** If the documentation is
  wrong or stale, so is the answer — that is a real failure I caught and
  wrote a test for, not a hypothetical.
- **Free tier only.** 20 requests/day/model is the binding constraint on
  everything.
- **Measured on a 10-document corpus.** Nothing here has been tested at
  realistic documentation scale.
- **No authentication, no rate limiting, no multi-user.** It is a CLI.

---

## If something goes wrong

| symptom | cause | fix |
|---|---|---|
| `No GEMINI_API_KEY` | no `.env`, or key not pasted in | `copy .env.example .env`, paste the key |
| `ModuleNotFoundError` | packages not installed, or wrong venv | activate the venv, `pip install -r requirements.txt` |
| `429 RESOURCE_EXHAUSTED` | daily free quota spent | wait for the reset, or use a different model in `.env` |
| hangs on first run | downloading the embedding model | wait once; it is cached after |
| empty answer | thinking tokens ate the output budget | already handled — it retries with double the budget |
| `dubious ownership` from git | Windows SID mismatch | `git config --global --add safe.directory D:/SSAI` |

Still stuck? `python app.py --check` first. It is designed to name the
problem and the fix.

---

## The twelve-week build

Everything above is the app. Everything below is how it got here — each
week has a `NOTES.md` with the concepts, the measured results, and the
questions a reviewer is likely to ask.

## Layout

| Path | What |
|---|---|
| `llm.py` | Shared model client: pinned model, retry/backoff, response cache |
| `week1/` | LLM foundations — tokens, temperature, embeddings (experiments) |
| `week2/` | Prompting, structured output, tool calling (notes) |
| `week3/` | The RAG app: `docs/` corpus, `rag.py` engine, `ask.py` CLI |
| `week4/` | Retrieval debugging: BM25, hybrid RRF, reranking, metrics |
| `week5/` | Error analysis: trace collection and taxonomy |
| `week6/` | Evaluation: eval set, rule checks, LLM-as-judge + judge validation |
| `week7/` | Agent loops: ReAct agent, fixed workflow, and the race between them |
| `week8/` | Agent failure modes: trajectory evals, prompt injection + defence |
| `week9/` | MCP: discovered tools, my own fastmcp server, the raw handshake |
| `week10/` | Multi-agent: a manager+2 specialists squad raced against the single agent |
| `week11/` | Production: per-request logging, the support drill, cost per request, failure -> test |
| `week12/` | Capstone: the demo script, known weak spots, the eval report |
| `app.py` | **The single entry point.** Everything above, behind one command |

## Commands

    python week1/01_tokens.py              tokenisation and cost
    python week1/05_embeddings.py          embeddings, local, no API
    python week3/ask.py                    the RAG app (demo question set)
    python week3/ask.py --chunks           chunk size comparison, no API
    python week4/measure.py --rerank       retrieval metrics, no API
    python week4/evidence_4092.py          chunk/rank evidence for one failure
    python week4/recheck.py                re-answer the failing question
    python week5/collect_traces.py         collect ~21 traces for analysis
    python week6/eval.py                   rule-based eval suite, before/after
    python week6/eval.py --judge --validate  LLM judge + agreement check
    python week7/race.py                   agent vs fixed workflow (~16 requests)
    python week8/trajectory.py             trajectory audit         (0 requests)
    python week8/injection.py              injection + defence      (~2 requests)
    python week8/measure.py                before/after on the fix  (~14 requests)
    python week9/show_handshake.py         raw MCP JSON-RPC         (0 requests)
    python week9/mcp_client.py             discover + call tools    (0 requests)
    python week9/prove_no_agent_change.py  second tool, no edits    (0 requests)
    python week9/agent_mcp.py              agent over MCP           (~3 requests)
    python week10/race.py                  squad vs single agent    (~20 requests)
    python week11/run_logged.py            logged run + noise       (~10 requests)
    python week11/find.py --stats          log health               (0 requests)
    python week11/find.py --deprecated     every known-bad answer   (0 requests)
    python week11/cost.py --all            cost before/after        (~8 requests)
    python week11/regress.py               regression suite, replay (0 requests)
    python week11/report.py                regenerate week11 RESULTS (0 requests)
    python app.py --check                  preflight                (0 requests)
    python app.py "your question"          the app                  (~3 requests)
    python app.py --eval                   full suite               (0 requests)
    python app.py --demo                   four-part demo           (~9 requests)

## Notes

Each week has a `NOTES.md` with the concepts, the measured results, and
answers to the likely evaluator questions.

`week11/RESULTS.md` is the one exception: it is GENERATED by
`python week11/report.py` from the logs, so its numbers cannot drift from
the data they describe. Edit the experiment, not the write-up.

## Key measured results

- Free tier is **20 requests/day per model** — hence the response cache in `llm.py`
- `temperature=0` is **not** reproducible on a thinking model; a fixed `seed` is needed
- Embeddings score `ERR-4032` vs `ERR-4033` at **0.970** — they encode
  "looks like an error code", not which one
- Document-level `hit-rate@3` was **blind** to a real failure; an
  answer-containment metric (`ANSWER@3`) exposed it
- Best single retrieval change: cross-encoder reranking,
  **ANSWER@3 0.667 → 0.833**
- The LLM judge agreed with hand-grading only **75%** of the time, both errors
  lenient — so its scores were **not** reported
- Week 7's agent carries **four** stop conditions (6 steps / 90s / 8 calls /
  repeat guard); the fixed workflow uses **1** LLM call per question and
  structurally cannot loop
- Week 8 found an **outcome-vs-trajectory gap of +0.250** - one run answered
  correctly on a path that skipped a required step, and was right only by luck
- A required-step gate took **trajectory pass rate 0.250 -> 1.000** and
  SKIPPED_STEP **3 -> 0**, at a cost of **+6 LLM calls**
- The agent was successfully **prompt-injected** through a poisoned doc chunk,
  then defended (sanitise + delimit + output validation)
- Week 9: adding a second MCP tool changed the agent by **zero bytes**,
  verified by sha256
- Week 10 (live, all 4 questions): the 3-agent squad scored **4/4** against
  the single agent's **2/4**, but cost **2.44x** the calls, **1.39x** the
  tokens and **4.57x** the wall-clock - and both single-agent failures were
  week 8's **SKIPPED_STEP**, the fix week 8's required-step gate already buys
  for about +1 call
