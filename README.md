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

## Commands

    python week1/01_tokens.py              tokenisation and cost
    python week1/05_embeddings.py          embeddings, local, no API
    python week3/ask.py                    the RAG app (demo question set)
    python week3/ask.py --chunks           chunk size comparison, no API
    python week4/measure.py --rerank       retrieval metrics, no API
    python week4/evidence_4092.py          chunk/rank evidence for one failure
    python week4/recheck.py                re-answer the failing question
    python week5/collect_traces.py         collect ~21 traces for analysis

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
