# Week 1 — Foundations: what I learned and what I measured

Every claim below was tested with a script in this folder. Where the result
contradicted the textbook answer, the measured result is recorded.

## 1. What a language model is

Predicts the next token, repeatedly, feeding its own output back as input.
That is the entire mechanism.

- Training compressed billions of documents into fixed weights. **The training
  text is not stored.** There is nothing to look up and nothing to cite.
- This is why hallucination happens: "plausible" and "true" are the same thing
  to it. It has no mechanism to tell them apart.
- This is why RAG exists: we cannot make it remember our documents, so we paste
  the relevant chunk into its input right before it answers.

## 2. Tokens  (`01_tokens.py`)

A token is a chunk of text from a fixed table built before training.
Rule of thumb, English: 1 token ~= 4 chars ~= 0.75 words.

| sample | chars/token |
|---|---|
| `payment failed` | 7.0 |
| `{"status": "settled"}` | 2.6 |
| `ORD-4471-XZ` | 1.8 |
| Tamil text | 0.7 |

- `ORD-4471-XZ` -> `['ORD','-','447','1','-X','Z']`. The model never sees `4471`
  as one thing, which is why LLMs are unreliable on exact IDs and codes.
- `"The payment failed."` = 3 words but 4 tokens (the `.` is its own token).
- Billing is per token, in and out.

## 3. Temperature and decoding  (`02`, `03`, `04`)

At each step the model outputs a probability over every token in its vocabulary.
**Decoding** is how one gets picked.

- **Greedy (temp 0):** always take the top token.
- **Sampling (temp > 0):** weighted random draw.
- **Temperature** reshapes the odds before the draw. Low = sharpen, high = flatten.
- **top-k** keeps the k likeliest tokens; **top-p** keeps the smallest set summing
  to p. Both delete candidates; temperature reweights them. They stack.
- **seed** fixes the random draw so a sampled result is repeatable.

### Measured, and it contradicted the textbook

1. **temp=0 is NOT always deterministic.** On `gemini-3.6-flash`, three temp-0
   calls gave three different sentences. Cause: the model generates hidden
   *thinking* tokens first, and that reasoning is itself sampled.
   -> For reproducibility use **temp=0 AND a fixed seed**.

2. **Temperature can be invisible.** On `gemini-3.5-flash-lite`, temp 2.0 with
   `top_p=1.0, top_k=200` returned "Velvet Bean" 3/3 on a deliberately open
   prompt. Isolated it with four hypotheses (`04_why_no_variation.py`):
   - `top_p` was not the filter (H1 ruled out).
   - Changing the **seed** did change the answer -> sampling IS happening.
   - The same test on `gemini-3.8-flash` gave 3 different names.
   -> Conclusion: `flash-lite` has a much more **peaked** output distribution.
      Small distilled models are more confident, so flattening a tall spike
      still leaves a spike. **Temperature widens the net; it does not add fish.**

3. **temp=0 does not prevent hallucination.** Asked about a non-existent Stripe
   setting `cascade_backoff_threshold`, the model invented a detailed
   explanation with a code example, at temperature 0.
   -> Temperature controls VARIETY, not TRUTH.

4. **Hallucination depends on question shape.** Asked about "clause 7 of the
   PT-2024 Policy" it correctly refused. Asked about a plausible-sounding
   library feature it confabulated. It refuses on named private documents;
   it invents where the question sounds like general knowledge.

## 4. Context window

A hard limit, counted in tokens, covering instructions + history + pasted
documents + the answer being generated.

- "Forgetting" in long chats = old turns dropped to fit.
- Bigger is not free: you pay per token, and accuracy drops for facts buried
  mid-context ("lost in the middle").
- This is why Week 3 chunks documents instead of pasting whole manuals.

## 5. Embeddings  (`05_embeddings.py`)

Text -> a vector of numbers representing meaning. `all-MiniLM-L6-v2` gives 384
numbers per text. Similarity = cosine of the angle between two vectors.

- **Static** (Word2Vec, GloVe): one fixed vector per word forever.
- **Contextual** (this model): the vector depends on the whole sentence.

Measured, contextual works:
- "The bank declined the charge on my card" vs "We charge the battery" = **0.211**
- same vs "The issuer rejected the transaction on my credit card" = **0.693**

Shared keyword scored LOW, shared meaning scored HIGH. That is contextual
embedding doing its job.

### Where embeddings fail — measured

| pair | similarity |
|---|---|
| `ERR-4032` vs `ERR-4033` | **0.970** |
| `INV-2024-881` vs `INV-2024-882` | **0.996** |

Embeddings encode "this looks like an error code", not WHICH code. For a
developer-docs RAG app this is the top failure risk. Week 4 fixes it with BM25
keyword search alongside the vector search (hybrid).

### Second failure — surface overlap beats meaning

Question: *"How do I get my money back?"*

| candidate | similarity | words shared |
|---|---|---|
| "Refunds are issued to the original card within 5 business days." | 0.409 | 0 |
| "Please put the money back in the petty cash box." | **0.509** | 2 |

**The wrong document won.** The phrase "money back" pulled the distractor to
the top. A bi-encoder squeezes each text into one vector *independently*, so it
never compares the question and the document against each other — it cannot
notice that "petty cash box" does not answer "how do I get MY money back".

That is precisely the gap a **cross-encoder reranker** fills (Week 4).

## 6. Encoder vs decoder

|  | Encoder | Decoder |
|---|---|---|
| Reads | whole text, both directions | left to right |
| Produces | one vector per text | next token, repeatedly |
| Used for | search, similarity | writing, answering |
| Example | BERT, all-MiniLM-L6-v2 | GPT, Claude, Gemini |

The Week 3 app uses **both**: encoder finds the chunk, decoder writes the answer.

## 7. Picking a model — practical findings

- Models get **retired**. `gemini-2.5-flash` returned 404 "no longer available
  to new users" mid-exercise.
- **Pin the version**, never use a `-latest` alias: Week 6 compares a before and
  an after score, and a silently upgraded model makes those incomparable.
- Free tier quota is **per day, per project, PER MODEL**.
  `gemini-3.6-flash` = 20 requests/day. Confirmed from the 429 body.
- Therefore: split by job. `gemini-3.5-flash-lite` as the workhorse,
  `gemini-3.8-flash` reserved for Week 6 judging. Two models = two quotas.

## 8. Engineering that came out of this  (`llm.py`)

- **Retry only what a delay can fix.** 429 and 5xx are retryable with
  exponential backoff. 400/401/403/404 are not — retrying a malformed request
  just fails four times and burns quota.
- **Cache responses to disk**, keyed on a hash of everything that affects the
  answer. Free tier is 20/day; without a cache, re-running an eval to fix a
  typo costs a day.
- **A cache will lie to you.** It silently invalidated experiment `02` — repeated
  identical calls were served from disk, so "all identical? True" proved nothing.
  Pass `use_cache=False` whenever the thing being measured IS variation.
- **Never truncate an error.** The 429 body names which quota, the limit, and a
  retry delay. Cutting it to 60 chars threw away the entire diagnosis.
