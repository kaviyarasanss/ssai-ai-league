# Weeks 1–9 — everything, on one page

**The whole project in one sentence:** I built a RAG app over developer
documentation, found it was wrong sometimes, learned to tell *which half* was
wrong, measured retrieval with a number, read 21 real traces to rank the
problems by hand, then built a one-command eval suite that proves a change
helped — caught my own AI judge being unreliable — and finally gave the same
task to an agent that chooses its own steps, and raced it against the fixed
pipeline to decide which one is actually worth shipping.

---

## THE NUMBERS (memorise these six)

| | |
|---|---|
| `ERR-4032` vs `ERR-4033` embedding similarity | **0.970** — embeddings can't tell codes apart |
| Free tier | **20 requests/day PER MODEL** |
| Week 3 result | **4/5** answerable correct, **2/2** out-of-scope refused, **1** failure |
| Week 4 one change (reranking) | `ANSWER@3` **0.667 → 0.833**, `MRR` 0.796 → 0.861 |
| Week 5 sample | **21 traces**, **5** false refusals, **0** hallucinations |
| Week 6 judge validation | **75%** agreement → **not trustworthy** |
| Week 7 agent budgets | **4** (steps 6 · 90s · 8 calls · repeat guard) |
| Week 7 cost shape | agent **2–3** LLM calls/question vs workflow **1** |
| Week 7 live race (run 1) | agent **2/4**, workflow **2/4** — 2 agent losses were *empty replies* |
| Week 8 outcome-vs-trajectory gap | **+0.250** — right answer, wrong path |
| Week 8 fix | trajectory **0.250 → 1.000**, SKIPPED_STEP **3 → 0**, cost **+6 calls** |
| Week 9 MCP | second tool added, agent changed by **0 bytes** (sha256 verified) |

---

# WEEK 1 — Foundations

**Language model** = predicts the next token, repeatedly. Training compressed
documents into weights; **the training text is not stored**. Nothing to look
up, nothing to cite. This is why hallucination happens and why RAG exists.

**Token** = a chunk of text from a fixed table built before training.
English ≈ 4 chars ≈ 0.75 words per token.

| sample | chars/token |
|---|---|
| `payment failed` | 7.0 |
| JSON | 2.6 |
| `ORD-4471-XZ` | 1.8 |
| Tamil | 0.7 |

`ORD-4471-XZ` → `['ORD','-','447','1','-X','Z']` — the model never sees `4471`
as one thing. **This is why LLMs are unreliable on exact IDs, and why week 4
adds keyword search.**

**Context window** = a hard token limit covering instructions + history +
pasted documents + the answer. "Forgetting" in long chats is old turns being
dropped. Bigger isn't free: you pay per token and accuracy drops for facts
buried mid-context ("lost in the middle").

**Decoding** = how one token gets picked from the probability distribution.
- **Greedy (temp 0)** = always the top token.
- **Sampling (temp > 0)** = weighted random draw.
- **Temperature** reshapes the odds before the draw. Low = sharpen, high = flatten.
- **top-k** keeps the k likeliest; **top-p** keeps the smallest set summing to p.
  Both *delete* candidates; temperature *reweights* them. They stack.
- **seed** fixes the random draw so a sampled result is repeatable.

**Embeddings** = text → a vector of numbers representing meaning.
- **Static** (Word2Vec, GloVe): one fixed vector per word forever.
- **Contextual** (ours): the vector depends on the whole sentence.

**Encoder vs decoder**

| | Encoder | Decoder |
|---|---|---|
| reads | whole text, both directions | left to right |
| produces | one vector per text | next token, repeatedly |
| for | search, similarity | writing, answering |
| e.g. | BERT, all-MiniLM-L6-v2 | GPT, Claude, Gemini |

The week 3 app uses **both**: encoder finds the chunk, decoder writes the answer.

### Measured, and it contradicted the textbook

1. **temp=0 is NOT always deterministic.** On `gemini-3.6-flash`, three temp-0
   calls gave three different sentences — hidden *thinking* tokens are
   themselves sampled. **Reproducibility needs temp=0 AND a fixed seed.**
2. **Temperature can be invisible.** On `flash-lite`, temp 2.0 with top_p=1.0
   and top_k=200 returned "Velvet Bean" 3/3 on a deliberately open prompt.
   Isolated with four hypotheses: top_p was not the filter; different *seeds*
   DID change the answer, so sampling happens; the same test on `3.8-flash`
   varied freely. **Conclusion: `flash-lite`'s distribution is far more
   peaked. Temperature widens the net; it doesn't add fish.**
3. **temp=0 does not prevent hallucination.** At temperature 0 it invented a
   detailed explanation of a non-existent Stripe setting, with a code example.
   **Temperature controls VARIETY, not TRUTH.**
4. **Hallucination depends on question shape.** It refused "clause 7 of policy
   X" but confabulated a plausible-sounding library feature. It refuses on
   named private documents; it invents where the question sounds like general
   knowledge.

### Errors and which to retry

| error | meaning | retry? |
|---|---|---|
| 400 INVALID_ARGUMENT | our request is malformed | **NO** — fix the code |
| 401 / 403 | bad or unauthorised key | **NO** |
| 404 NOT_FOUND | model retired | **NO** — change the model |
| 429 RESOURCE_EXHAUSTED | quota / too fast | **YES**, with backoff |
| 5xx | their servers | **YES**, with backoff |

Retry only what a *delay* could fix. Retrying a 400 four times fails four
times and burns four requests.

---

# WEEK 2 — Prompting, structured output, tool calling

**Prompt anatomy**: system instruction · task · context · examples · output
format · constraints. **Good examples beat long instructions.**

**Zero-shot / one-shot / few-shot** = 0, 1, or 2–5 examples in the prompt.
Few-shot wins on specific formats and edge cases; you pay for those tokens
on every call.

**Chain-of-Thought** = ask it to reason step by step. Works because each
reasoning token becomes input for the next. Modern thinking models do it
internally — those hidden tokens still cost money and count against
`max_output_tokens`.

**Self-consistency** = run the same CoT prompt N times at temp > 0 and take
the **majority** answer (not the "best" — there's no judge). Useless on a
peaked model: all N agree and you paid N times.

**Task decomposition** = split one hard prompt into several easy chained ones.
Easier to debug, cheaper per step. The seed of agent loops.

**Structured output**, weakest to strongest: (1) ask nicely for JSON,
(2) a response schema the API enforces during decoding, (3) validate in your
own code and retry.

**Pydantic** = declare the data shape as a class, validate real data against
it. A NestJS DTO + class-validator, in Python.
`urgency: int = Field(ge=1, le=5)` → model returns 9 → **validation fails**,
you catch it instead of storing it.

**instructor** = wraps the client so you pass a Pydantic model and get a
validated object back; handles schema, parsing and retry.

**Validation & retry** ≠ API retry. API retry handles transport (429, 5xx).
Validation retry handles a *well-formed response with wrong content* — and you
must **feed the validation error back**, or the model repeats the mistake.

**Tool calling.** The model **cannot run anything**. It emits
`{"name": "lookup_order", "args": {...}}`. **YOUR code runs the function**,
returns the result, and the model writes the final answer. *Who runs the tool?
Your code. Always.* **Parallel tool calls** = several requested at once when
independent. **AFC** (Gemini SDK) does the loop for you and hides it.

**Guardrails** = checks in your own code, not requests inside the prompt.
Input (reject empty/oversized, strip secrets), output (validate schema, check
a citation exists, confirm a refusal), fail safe (never crash, never pass
unvalidated output to a real action), tool-level (a tool that moves money
needs its own authorisation — the model asking is not authorisation).

**Prompt injection** works because **the model sees instructions and data as
one token stream** — there's no privileged channel. **Indirect** injection is
the RAG-relevant version: the attack text lives in a *retrieved document*.
Mitigations: delimit and label untrusted text as data, never let model output
trigger a privileged action without your own check, least-privilege tools.

**Key hygiene**: key in `.env`, `.env` in `.gitignore`, `.env.example`
committed with the value blanked. Never in source, logs, or a commit.

---

# WEEK 3 — The RAG app

**Why RAG:** the weights contain no copy of your documents and you can't add
them. You can only put the right text in front of the model at question time.
**Open-book exam instead of closed-book.**

### Two phases — say this distinction out loud

    INDEXING (once, no API calls)
      10 documents → chunk → 47 chunks → embed → 47×384 matrix

    ANSWERING (per question)
      question → embed → cosine vs all 47 → top 3 → prompt → answer + [n]
                                                              ↑ the only API call

**Five of six steps cost nothing.** That's why the course survives on 20
requests/day.

**Chunking.** Split on `##` headings first (a real topic boundary), then by
size if still too long. **Why chunk at all:** the context window is finite,
and a whole document in one vector is the *average* of everything in it — it
matches everything weakly and nothing strongly.

**Overlap** repeats the last N chars at the start of the next chunk, so a fact
on a boundary survives intact somewhere.

**Chunk size trade-off** — small = sharp match but the answer may be cut;
large = complete context but the vector is diluted and you pay more tokens.

**Embedding**: `all-MiniLM-L6-v2`, 384 dims, a **bi-encoder** — encodes each
chunk *independently*, so all 47 vectors are precomputed once.

**Search**: `scores = matrix @ q`. **Why a bare dot product is the cosine:**
we embed with `normalize_embeddings=True`, so every vector has length 1;
cosine = dot ÷ (|a|·|b|) = dot ÷ 1. One matrix multiply scores all 47.

**top-K** (K=3): too small and the answer isn't there; too large and you stuff
the prompt with noise and give the model more to cite wrongly.

**Vector DBs & HNSW.** We use brute-force exact search over 47 vectors —
instant and exact. A vector DB earns its place at ~100k+ vectors using
**HNSW** (Hierarchical Navigable Small World), which walks a layered
neighbour graph instead of scanning everything. **HNSW is approximate** — it
can miss the true best match. You trade recall for speed.
**Qdrant** = standalone server · **Chroma** = embedded, prototypes ·
**pgvector** = a Postgres extension, so vectors sit beside relational data.

**Metadata filtering** = narrow candidates by attributes before/during search
(`doc_type`, `version`). A search that only ever looks at the right 5% is both
faster and more accurate.

**Grounded generation** = answer ONLY from the supplied passages, cite the
passage number, say "I don't know" if it isn't there.

**How citations work.** We number the passages `[1] [2] [3]` in the prompt —
those numbers are **our invention**, a temporary index into the list we just
handed it. The model replies "…insufficient funds [1]", we regex the markers
back out and map `1 → 04_error_codes.md > ERR-4032 vs ERR-4033`. **The model
never names a file** — a digit can't be garbled, and a marker outside 1..3 is
instantly detectable as invalid.

**Two refusal guards.** (1) If the top score < `MIN_SCORE` (0.25), refuse
**without calling the model** — free, and stops a weak match becoming a
confident answer. (2) The system prompt instructs the model to refuse.

### Result and the one failure

4/5 answerable correct with citations · 2/2 out-of-scope refused ·
chunk sizes 300/600/1200 compared.

**The failure:** *"Which decline codes cascade, and which do not?"* → "I don't
know", although all three chunks came from the correct file. The 640-char
`## Cascading` section split at chunk_size=600 into chunk A (600 chars, the
full table) and chunk B (140 chars, the overlap tail, no table). **B scored
0.499 and took the last slot; A scored ~0.433 and missed.**

**Why the useless chunk won:** cosine measures *direction*, and a short chunk
has a concentrated direction. B is 140 chars almost entirely about cascading.
A averages a heading, a code block, prose and a table. **Short and shallow
beat long and correct.**

**Also measured:** the Salesforce question scored **0.721** — higher than the
ERR-4032 question that answered *correctly* (0.682) — and had no answer
present. **Similarity measures topic, not containment.** A score can't read;
only the model can.

---

# WEEK 4 — Debugging retrieval

**Three kinds of wrong** (the brief names two; we found a third):

| | Retrieval | Chunking/ranking | Generation |
|---|---|---|---|
| right doc fetched? | no | **yes** | yes |
| answer intact in prompt? | — | **no** | yes |
| fix | search | chunk size / reranking | prompt |

**Retrieval quality is pure maths — no LLM, no quota.** That's why week 4
comes before week 6.

**Metrics (k=3)**
- **hit-rate@k** — was a gold document in the top k?
- **recall@k** — what fraction of gold documents were in the top k?
- **MRR** — 1/(rank of first gold doc), averaged. Rank 1 → 1.0, rank 2 → 0.5.
  **Rewards putting it FIRST**, not merely somewhere.
- **ANSWER@k** (ours) — did a retrieved **chunk** actually contain the needed text?

**BM25** = keyword/sparse retrieval. Scores by word overlap, rare words
weighted higher, long docs penalised. **Knows nothing about meaning** — which
is exactly why it complements dense search: it knows `ERR-4032` differs from
`ERR-4033`. Library `rank-bm25`, no model download.

**RRF (Reciprocal Rank Fusion)** merges two ranked lists by **position, not
score**, because cosine (0–1) and BM25 (0–30+) aren't comparable —
add them and BM25 wins everything.
`score = Σ 1/(60 + rank)`. **Agreement across methods wins.**

**Bi- vs cross-encoder**
- **Bi-encoder**: encodes question and chunk *separately*. Fast, precomputable.
  The two texts never meet, so it can't reason about how they relate.
- **Cross-encoder**: both **together** → one relevance score. Far more
  accurate, far slower, nothing precomputable. Runs on a shortlist only.
- Pattern: **retrieve 12 cheaply → rerank properly → keep 3.**
  Hosted: Cohere Rerank. Open: BGE-Reranker, `ms-marco-MiniLM` (ours).

**MMR** = penalise a candidate for resembling ones already chosen, so you
don't return three near-identical chunks. **Query rewriting** = rewrite the
user's messy wording before searching. **HyDE** = generate a fake answer and
search with *that*, since a fake answer looks more like a document than a
question does.

### Results

    strategy                              ANSWER@3   hit@3  recall@3    MRR
    A  BASELINE dense only                   0.667   0.889     0.861  0.796
    B  bm25 only                             0.722   0.833     0.833  0.769
    C  hybrid dense+bm25 RRF                 0.778   0.889     0.889  0.833
    D  dense only, chunk 1200                0.722   0.889     0.861  0.796
    E  dense + cross-encoder rerank          0.833   0.889     0.889  0.861
    F  hybrid + rerank (TWO changes)         0.889   0.944     0.944  0.889

**hit@3 is 0.889 for A, C, D and E — four different systems, one identical
score. The metric could not tell them apart.** ANSWER@3 separates them
0.667–0.833.

**The one change: cross-encoder reranking.** `ANSWER@3 0.667 → 0.833 (+0.167)`,
`MRR 0.796 → 0.861`. Chosen because the failure was a *ranking* failure — the
right chunk was already in the pool, just outranked.

**Proof on the real answer:** the cascade question went from "I don't know" to
the complete four-row table, and the table chunk moved from missing the top 3
to **rank 1**. The two questions that already passed still pass.

### What it did NOT fix, and why

**ERR-4092.** Exactly one chunk of 47 contains it — in a section called
*Timing* on the **refunds** page. `04_error_codes.md` doesn't mention it.

    strategy                     rank of the right chunk   top-K needed
    dense (baseline)                    28 of 47              k >= 28
    BM25 only                            1 of 47              k >= 1
    hybrid dense+bm25 RRF               10 of 47              k >= 10
    dense top-12 then rerank        not in ranking            never

**Reranking can only reorder what retrieval already found.** At rank 28 it
never enters the top-12 pool, so the cross-encoder never sees it.

**Why hybrid also failed — the arithmetic:**

    ERR-4092 chunk:  1/(60+28) + 1/(60+1) = 0.0114 + 0.0164 = 0.0278
    a wrong chunk:   1/(60+3)  + 1/(60+5) = 0.0159 + 0.0154 = 0.0313  ← wins

BM25 ranked it **first**. RRF demoted it to **10th**, because a chunk both
retrievers rank *moderately* beats one that a single retriever ranks first.
Tuning needs `k ≤ 1` or a **5× BM25 weight** — both extreme enough to wreck
the semantic questions. **The fix is structural: route `ERR-\d{4}` queries
straight to BM25, or filter on metadata.**

**"too small"** — vocabulary gap: user says "too small", doc says "Amount
below minimum". Needs query rewriting or HyDE, not better ranking.

**Bug found:** the BM25 tokenizer absorbed trailing punctuation, so
`ERR-4092.` in prose became `err-4092.` and never matched `err-4092`. One
character silently broke exact-code search. Found by testing BM25 **alone**
before fusing it.

---

# WEEK 5 — Error analysis

**Why:** week 4 fixed what we happened to notice — and we only noticed it
because it was 1 of 7 questions we tried. **"Fix what you noticed" is a
terrible strategy.**

**Trace** = the complete record of one request: question, every retrieved
chunk *with score and full text*, the answer, the citations. Complete enough
to replay later.

**Open coding** = write your honest note per failure **before** deciding
categories. Decide categories first and you force every failure into a box you
already had, and never discover the one you didn't know about.

**Error taxonomy** = those notes, grouped, with names a stranger understands.
`"exact identifier lives in an unexpected document"` ✅ ·
`"retrieval issues"` ❌.

**Frequency × severity** — you can't fix everything. For a payments docs bot:
**a confidently wrong answer ≫ a false refusal.** Refusing is annoying;
a wrong retry policy could cause a double charge.

**Random vs curated sampling** — we have no real user traffic, so our 21 are a
**stratified** sample (exact_code 7, semantic 8, mixed 3, out_of_scope 3) that
deliberately **includes** known failures. The trap the brief warns about is
keeping only the nice examples; this is the opposite.

**Benchmarks (MMLU, HumanEval) vs your app** — they measure general model
ability and say nothing about whether *your* app finds *your* documents.

**Write a prediction first** — it stops you rationalising afterwards.

### Facts before judgement

    traces 21 · answerable 18
    answer text retrieved   12/18
    right document          16/18
    refused anyway           5/18   ← false refusals
    carried a citation      11/18
    out-of-scope refused      3/3
    hallucinations              0

**The gap between 16 and 12 is four traces where retrieval found the right
file and still missed the answer.**

### The taxonomy, ranked

| rank | problem | freq | sev | score |
|---|---|---|---|---|
| **1** | **P1** answer in the right document, its chunk loses the ranking | 4/18 | high | **12** |
| **2** | **P2** citations dropped when the model writes `[2, 3]` | 2/18 | high | **6** |
| 3 | **P3** exact identifier in an unexpected document | 1/18 | high | 3 |
| 4 | **P4** the user's words don't appear in the documents | 1/18 | med | 2 |

**P2 was our own bug**: `re.findall(r"\[(\d+)\]")` matches `[2]` but **not**
`[2, 3]`. The model cited two passages for one fact — *more* precise, not
less — and our parser threw both away.

**Severity finding that matters more than the ranking:** every failure was a
refusal or an omission. **Zero hallucinations in 21 traces.** The app fails
**silent, not wrong** — the right direction for payments documentation.

**Prediction written before week 6:** P1 3 of 4 fixed · P2 untouched by
reranking · P3 not fixed · P4 not fixed · `answer_available 0.667 → ~0.83`,
false refusals 5 → ~2.

---

# WEEK 6 — Evals

**Eval set** = questions + a way to score the answer. The unit test suite for
an app whose output is text.

**Regression tests from failures** = every real failure becomes a permanent
test. Our 8 failures are tagged P1–P4; the 13 that already passed are
**guards** — a change that fixes P1 but breaks those isn't an improvement.

**Assertion checks — do these first, they're free.**
`answer_available` · `no_false_refusal` · `has_citation` ·
`citations_valid` · `refused_correctly`.
`refused_correctly` is the one people forget: it stops "fix the false
refusals" becoming "answer everything, right or wrong".

**LLM-as-judge** for what a rule can't check. It gets **three things only**:
the same top-3 passages, the question, the answer. It is **denied** the gold
label, the required text, and the other 44 chunks.
**Why blind?** "Faithful" means *grounded in the retrieved context*, not *true
in the world*. If it saw the corpus it would be grading retrieval — already
measured by rules, free and exact — and one failure would be counted twice.

| layer | graded by | sees the gold label? |
|---|---|---|
| retrieval | rules | **yes** |
| generation | judge | **no** |

**RAGAS** splits it four ways: **faithfulness** and **answer relevancy** judge
the *answer* (LLM needed); **context precision** and **context recall** judge
the *retrieval* — which we already measure in week 4 as ANSWER@3, hit-rate@3
and recall@3, arithmetic and exact. **So LLM calls are spent only on the two
that need reading.**

**Binary, not 1–10.** Nobody reliably tells a 6 from a 7 and the same answer
drifts. Decisively: **a human can agree or disagree with a binary verdict** —
that's what makes validation possible.

**G-Eval** = give the judge explicit criteria and make it reason through them
*before* committing to a verdict. Reasoning-first beats a bare verdict.

**Judge validation** = you grade the same answers, then compare. Report the
two error directions separately: **too lenient hides real failures** (bad),
**too harsh** is merely annoying. And a **different model** judges — a model
grading its own output is biased toward it, and per-model quota is separate.

### Results

    check                    BEFORE    AFTER    delta
    answer_available          0.667    0.833   +0.167
    no_false_refusal          0.722    0.889   +0.167
    has_citation              0.846    0.938   +0.091
    citations_valid           1.000    1.000   +0.000
    refused_correctly         1.000    1.000   +0.000     ← guard held

    problem                    BEFORE      AFTER
    (previously passing)       13/13       13/13          ← guard held
    P1  wrong chunk             0/4         3/4
    P2  citations dropped       0/2         1/2
    P3  code in odd document    0/1         0/1
    P4  vocabulary gap          0/1         0/1

    citation regex (own change):  old 11/13 → fixed 13/13

False refusals **5 → 2**. Zero regressions. Out-of-scope still 3/3 refused.

**Week 5's predictions: 4 of 5 correct, two exactly** (3/4 · 0.833 · 5 → 2).

**Prediction 2 was WRONG and it's the best finding of the week.** I said
reranking couldn't touch a regex in our own code. P2 went 0/2 → 1/2 — because
reranking changed *which passages* were retrieved, which changed how the model
**phrased** its citations: one case emitted `[1]` instead of `[2, 3]`, so the
buggy parser caught it by luck. **The bug wasn't fixed; it was accidentally
sidestepped.** A per-problem-type table exposes that; one overall score would
have recorded "P2 improved" and I'd have believed it.

### The judge

    agreement 75% (6/8)   too LENIENT 2   too HARSH 0
    -> NOT TRUSTWORTHY - do not report its numbers

**`relevant 8/8`, with the identical one-line reason six times.** A judge
rubber-stamping, not evaluating. Trusting it would have reported perfect
relevancy on an app with 5 false refusals.

- **C04 — genuine leniency.** "*How* should I back off" answered with "retry
  with exponential backoff", omitting the documented 1s/2s/4s/8s/16s + 30%
  jitter. Fixed: the prompt now carries an explicit act-on-it test.
- **C15 — not a judge defect.** Its reasoning: *"The context lacks the answer,
  so the refusal is relevant."* Correct given what it could see. The human
  graded end-to-end; the judge grades generation-only. **The rules already
  caught it** as `answer_available: False`.

**Genuine defects: 1 of 8 (88%) on the criterion the judge can assess.
Reported number stays the measured 75%.**

---

# TOP 12 EVALUATOR QUESTIONS

**1. Why does the model hallucinate?**
It generates the statistically likely continuation from patterns learned in
training. The training text isn't stored, so it can't check itself. Plausible
and true are the same thing to it.

**2. Does temperature=0 stop hallucination?**
No. It makes the hallucination *repeatable*. I measured it: at temp 0 it
invented a detailed explanation of a non-existent SDK setting.

**3. Is temperature=0 deterministic?**
In principle. **I measured that it isn't on a thinking model** — hidden
reasoning tokens are themselves sampled. You need temp=0 **and** a fixed seed.

**4. Why chunk instead of embedding whole documents?**
A whole document in one vector is the average of everything in it, so it
matches everything weakly and nothing strongly. Also the context window is
finite.

**5. Why is your similarity just `matrix @ q`?**
Both sides are normalised to unit length, so cosine = dot ÷ (1·1) = dot. One
matrix multiply scores every chunk.

**6. What's the weakest part of your system?**
Exact identifiers. `ERR-4032` vs `ERR-4033` embed at **0.970** — the vector
encodes "looks like an error code", not which one. For a developer-docs corpus
full of codes that's the top risk.

**7. Who runs the tool in tool calling?**
My code. The model only emits a JSON request. It cannot execute anything.

**8. Why didn't you use a vector database?**
At 47 chunks brute-force is instant and **exact**. A vector DB with HNSW buys
speed at scale by giving up exactness — a trade I don't need yet.

**9. How do you know a change helped?**
A 21-case eval suite, one command, before/after **per problem type**, with the
13 previously-passing cases as regression guards. `ANSWER@3 0.667 → 0.833`,
false refusals 5 → 2, zero regressions.

**10. Why not just retry every error?**
Retrying a 400 burns four requests to fail four times. Retry only what a delay
could plausibly fix — 429 and 5xx, never 400/401/403/404.

**11. Did you trust your AI judge?**
No. I validated it against my own grading on 8 answers: **75% agreement, both
errors lenient, so I did not report its numbers.** It passed 8/8 on relevancy
with the same one-line reason six times — the signature of a judge that isn't
discriminating.

**12. What would you do next?**
Route `ERR-\d{4}` queries to BM25 (P3 — proven unreachable by reranking, the
chunk ranks 28th of 47), add query rewriting for the vocabulary gap (P4), and
re-validate the sharpened judge.

---

# WEEK 7 — Agent loops

**The shift.** Weeks 3–6 were a **pipeline** — retrieve → prompt → answer,
one fixed shape. Week 7 is a **loop** where the model picks the next step.

```
THOUGHT      why it needs something
ACTION       names a tool + input
OBSERVATION  ← OUR CODE runs the tool and pastes the result back
FINAL        the answer
```

That is **ReAct** = Reason + Act.

**The rule everything hangs off: the model never executes anything.** It
emits text naming a tool; our Python parses it, calls the function, and feeds
the result back. Same as week 2 tool calling — we just drive the loop by hand
so every step is visible.

**Second rule, follows from the first: the API is stateless.** The model
remembers nothing between calls. "Agent memory" is us re-sending the whole
transcript every turn. That transcript is the `scratchpad`, a Python list.

**Why ever use one:** the path is *data-dependent*. "ERR-4092 on a refund"
needs code lookup → *discover* it's a refund-window problem → then refund
policy. Step 2 is unknowable until step 1 returns. A pipeline can't say
"it depends".

### Tool design — the model picks by reading the DESCRIPTION and nothing else

Each says **what / USE FOR / DO NOT USE FOR**. Two deliberately complementary
tools, the same dense/sparse split measured in weeks 1 and 4:

| tool | mechanism | good at | measured weakness |
|---|---|---|---|
| `search_docs` | dense + cross-encoder rerank | prose questions | ERR-4032 vs ERR-4033 at **0.970** cosine |
| `lookup_error_code` | BM25 exact keyword | one `ERR-####` | useless for prose |

`lookup_error_code` is the **structural fix for week 5's P3**: ERR-4092's
chunk ranks **28th of 47** by dense search, and week 6 proved reranking
couldn't reach it — *a reranker only reorders what retrieval already handed
it.* The fix wasn't a better ranker, it was a different retrieval mechanism.

Guards, each earning its place: regex-validate the input and return a
*helpful message* (the error text is part of the tool's interface); keep only
BM25 hits that literally contain the code (a near-miss would answer about the
**wrong code**); an unknown tool name returns the available list so the model
can recover instead of crashing.

`init()` builds the index **once**, shared by both racers — so the race
compares control flows, not two indexes. (Week 6's symmetry lesson.)

### Stop conditions — four, all checked BEFORE spending

| budget | value | catches |
|---|---|---|
| `max_steps` | 6 | model that never says FINAL |
| `max_seconds` | 90 | slow or hanging tool |
| `max_calls` | 8 | cost cap — **counts memory calls too** |
| repeat guard | — | same action **and** input twice in a row |

`stop_reason` is **returned in the trace**, not printed. An agent that stops
is fine; one that stops *silently* is undebuggable — week 5's tracing lesson
applied to control flow. The `for...else` is what makes the step budget
honest: `else` runs only if the loop never hit `break`.

### Memory

| kind | here |
|---|---|
| short-term | the `scratchpad`, re-sent whole every turn |
| summarisation | past 6 entries, **one** LLM call compresses the oldest into 2 lines, last 4 kept verbatim — **compress, don't drop** |
| long-term | not built; would be a vector store or `mem0` keyed by user — week 3 RAG pointed at past conversations instead of docs |

Why it exists: finite context, per-token cost, and week 1's **lost in the
middle** — a long scratchpad *buries* the useful part.

### The race

`workflow.py` does the same task with **no LLM in the control flow**: regex
for `ERR-####` → exact lookup → semantic search → **one** compose call.
Always 1 call, `stop_reason: "fixed sequence - cannot loop"`.

That's the honest comparison — not agent vs nothing, but agent vs *the
sensible thing you'd build if you already knew the steps*.

Reliability is **measured, not eyeballed**: each question carries a list of
facts the answer must contain, matched with week 4's whitespace-insensitive
`contains()`. This is week 6's ANSWER@ metric reused — after `hit-rate@3`
scored **0.889 for four materially different strategies** and passed a
question the app answered wrong.

Quota protection (20 req/day/model, a full race is ~16): every finished
question checkpoints immediately, a re-run **skips** finished ones, and a
quota `SystemExit` prints the partial scoreboard. Cached replays cost **0**.

### Which would you ship?

**The fixed workflow, when you already know the steps** — 1 call vs 3–5,
faster, and it *structurally cannot loop*. Most real "AI agent" product work
is honestly this.

**The agent, when the path genuinely depends on what it finds** — an unknown
number of lookups, or a next step only knowable after the previous result.

**The trap:** an agent on a task whose steps you already knew. You pay the
multiplier, take on the loop risk, and get the same answer.

### Week 7 evaluator Q&A

**Who runs the tool?** Our code. The model only emits text naming a tool. It
has no execution ability at all.

**How does it remember previous steps if the API is stateless?** It doesn't —
we do. The full scratchpad is re-sent in the prompt every turn.

**What stops an infinite loop?** Four budgets checked before spending, plus a
repeat guard, and every exit path sets a `stop_reason` returned in the trace.

**Why add a second tool instead of improving search?** Because week 6 showed
reranking couldn't fix it — the chunk ranked 28/47 was never in the pool a
reranker sees. Different failure, different mechanism.

**Workflow vs agent, in one line?** Who decides the control flow: I did, at
code-writing time, or the model does, at runtime, per step.

**How do you know the loop is safe?** Every path is tested with the network
stubbed out and zero API calls — repeat guard, malformed reply, empty reply
(with and without budget to retry), step cap, call cap, time cap (which stops
at **0 calls**), unknown tool name, and the summarisation path (10 steps → 12
calls, compression counted). See `week7/RESULTS.md`.

### The live race — what actually happened

Run 1: **agent 2/4, workflow 2/4**; agent 8 calls / 25.7s, workflow 4 calls /
7.4s.

Both agent losses were **empty model replies**, not wrong answers. Cause:
`max_output_tokens` caps *visible output and hidden thinking tokens together*,
and 700 was too small — on the harder turns the model spent the whole budget
thinking and returned an empty string. **Week 1's hidden-thinking-tokens
finding resurfacing as a control-flow bug.**

What did *not* happen matters: the loop didn't hang, didn't retry forever,
didn't invent an answer. It detected the unusable reply, stopped, and recorded
why — the safety machinery worked, it just had nothing to work with.

Fix: `REPLY_TOKENS = 2000`, and an empty reply now earns **one** retry at
double budget with a format reminder, under its own distinct `stop_reason` so
"empty" and "malformed" are never conflated again. The retry is skipped when
the call budget is spent, so the fix cannot blow the cost cap.

The workflow's two losses are a *different* problem: `jitter` and `24 hours`
live in a **different chunk of the same file** from the one retrieved. One
search can't see the gap — which is exactly the case an agent should win by
searching a second time. Run 1 couldn't test that, because the agent never got
to reply on those questions.

---

# WEEK 8 — Agent failure modes & trajectory evals

**The one idea.** Weeks 3–7 graded the ANSWER. Week 8 grades the PATH.
A right answer reached by a lucky route is not a working agent — it is a coin
that has not landed wrong yet. Same lesson as week 6's blind `hit-rate@3`:
**outcome is that blind metric, for agents.**

### The failure taxonomy
`SKIPPED_STEP` · `WRONG_TOOL` · `MADE_UP_INPUT` · `LOOPED` · `GAVE_UP_QUIET`
Naming a failure lets you count it; counting lets you prove a fix worked.

### The four numbers
outcome pass rate · trajectory pass rate · **the gap** between them ·
tool-choice accuracy · cost per task **mean and p99** (p99 because the mean
hides the one run that loops and bills you).

### What we found — the gap, from real traces, 0 API calls
```
outcome 2/4 = 0.500   trajectory 1/4 = 0.250   THE GAP +0.250
```
**Q2 is the finding.** The agent answered ERR-4092 correctly after ONE tool
call, skipping the policy search. Right only because ERR-4092's chunk sits in
`08_refunds.md`, which carries both required facts. Q1 proves it is luck:
ERR-4033's chunk is in `04_error_codes.md`, which has no cascade policy — so
there it *had* to take two steps. Same shortcut, different code, wrong answer.

### Prompt injection
Hidden instructions inside a document the agent reads. The agent **cannot
tell your instructions from the text** — both arrive as the same tokens in the
same prompt. *Indirect* injection is the dangerous kind: the attacker never
talks to your agent, they only need write access to something it retrieves.

**Placement beats payload.** The first attempt appended the payload as a new
section and never fired — that chunk is never retrieved. Moving it INSIDE the
`## Timing` section, the chunk `lookup_error_code` hits by BM25 exact match,
made it work. *An injection only fires if it lands in a chunk retrieval
actually returns.*

Defences: **sanitise** (strip instruction-shaped lines) · **delimit & label**
(fence it, call it quoted data) · **validate output** (block addresses/links/
codes absent from the clean corpus). Result: `BEFORE hijacked → AFTER clean`.
All three are filters. The structural one is **least privilege** —
`lookup_error_code` takes only `ERR-####` and can do nothing else, so a
hijacked agent can't make it send mail. *Patterns raise the attacker's cost;
scoping caps the damage.*

### The fix and its number
Top failure `SKIPPED_STEP` (3/4). Fix: a **required-step gate** — reject a
FINAL when a required tool was never called, say what was skipped, continue.
Bounded at 2 pushes so the gate can't loop.

| | before | after |
|---|---|---|
| trajectory | 0.250 | **1.000** |
| outcome | 0.500 | 0.750 |
| LLM calls | 8 | **14** |
| SKIPPED_STEP | 3 | **0** |

**Read the trajectory row, not the outcome row.** Outcome can stay flat while
the fix works perfectly — a lucky right answer was already a pass. What the
fix removes is the luck. The +6 calls is the honest price: the gate *buys* a
correct path. A trade, not a free win.

### What could still get through
Reworded payloads · encoded/split payloads · exfiltration needing no new
address · a poisoned **tool result** rather than a doc · English-only patterns
· **and the gate checks WHICH tools ran, not whether the agent used what they
returned.** That last one is my own fix's limit — say it before you're asked.

---

# WEEK 9 — MCP

**The problem.** Week 7's tools were a dict inside the agent. Adding one meant
editing the agent; nobody else could reuse it. MCP is a standard **socket**.

**Honest framing:** MCP does **not** make the AI smarter. It's plumbing. It
wins on **reuse and swapping**, not answer quality.

### The three roles
**host** = the app, *where the model runs* · **client** = the connector that
speaks MCP · **server** = offers tools, **holds no model**.

**Where does the AI run?** On the host, never the server. The server has no
model, no key, no prompt — it runs plain functions and doesn't know whether
the caller is an AI. The model only picks WHICH tool; our code does the call.

### The whole protocol — JSON-RPC 2.0
```
--> initialize                 <-- result
--> notifications/initialized  (no id = no reply expected)
--> tools/list                 <-- [{name, description, inputSchema}]   <-- DISCOVERY
--> tools/call                 <-- content blocks
```
`id` present = "I expect an answer". That's all of MCP.

**Transports:** stdio (subprocess, stdin/stdout — local tool; a stray
`print()` corrupts the stream) vs HTTP (remote, many hosts).

### Discovery
```python
# week 7                      # week 9
TOOLS = {"search_docs": {…}}  tools = await session.list_tools()
```
The agent builds its system prompt from descriptions off the wire. With
fastmcp the tool's **docstring** becomes that description — so the week 7 rule
holds: *the description is the interface.*

### The proof (0 API calls)
Hash the agent → discover against a 1-tool server → against a 2-tool server →
hash again. Tool list changes, **agent bytes don't**, and no tool name appears
anywhere in the agent file. *That strict check caught a real violation: the
first `agent_mcp.py` named both tools in its own docstring.*

### Recoverable errors
Unknown tool returns `{"isError": true}` **inside a result**, not a transport
failure — session stays open, agent can try something else.

### Safety
Server is **read-only by design**. Reversed: before trusting someone else's
server, ask what its tools can actually do and who wrote them — a
`delete_file` tool is one `tools/call` away. And an MCP tool result is
untrusted input exactly like a retrieved document: week 8 applies to it.

---

# THINGS I GOT WRONG (say these — they're the strongest material)

1. **"temp=0 gives identical output."** It didn't. Hidden thinking tokens are
   sampled.
2. **"The cascade table was sliced by the chunk boundary."** It wasn't —
   dumping the chunk text showed it intact. The real cause was a 140-char
   overlap *fragment* outranking the complete chunk.
3. **A response cache silently invalidated an experiment.** Repeat calls were
   served from disk, so "all identical" proved nothing. A cache is right for
   saving quota and **wrong** when measuring variation.
4. **My eval applied the refusal guard to one config only** — silently making
   it *two* changes. A stub run caught it. **An unfair comparison doesn't
   announce itself; it produces a number that looks fine and means nothing.**
5. **My retrieval metric was blind to my worst failure.** `hit-rate@3` scored
   0.889 and marked as PASS a question the app answered wrong, because it
   measures *files* and the failure was at *chunk* level.
6. **"Reranking can't affect the citation bug."** It did — 0/2 → 1/2 — by
   changing which passages were retrieved and therefore how the model phrased
   its citations. The bug was sidestepped, not fixed.
7. **I predicted Q4 would be decided by retrieval.** It was decided by
   *infrastructure* — an output-token budget too small for a thinking model,
   so the agent returned nothing at all on two of four questions. **The
   experiment I designed could not have answered the question I asked, and
   only running it revealed that.** Same shape as #4: a broken comparison
   doesn't announce itself.
8. **My injection didn't fire the first time.** I appended the payload as a
   new section, and that chunk is never retrieved — so the attack silently
   could not land. Placement, not payload, was the variable. *An experiment
   that cannot fire looks exactly like a defence that works.*
9. **My own MCP proof failed me.** `agent_mcp.py` claimed in its docstring
   that it named no tools — while naming two of them, in that very sentence.
   The strict check caught it. **Write the test so it can fail you.**
