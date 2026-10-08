# SSAI — AI Engineering League (Track E: Developer Documentation)

Week-by-week build of a RAG application over developer documentation, with
retrieval debugging, error analysis and automatic evaluation.

## Setup

    python -m venv .venv
    .\.venv\Scripts\Activate.ps1        # Windows
    pip install -r requirements.txt
    copy .env.example .env              # then paste your Gemini API key

Get a free key at https://aistudio.google.com

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

## Notes

Each week has a `NOTES.md` with the concepts, the measured results, and
answers to the likely evaluator questions.

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
