# Day 14 — Fine-Tuning Prep Notes

Analysis of Days 10–13 test logs to separate issues that fine-tuning could plausibly fix
(behavior — tone, format, adherence to rules) from those it cannot (retrieval — getting the
right data in front of the model).

**Bottom line:** Two of the three recurring issues are behavioral and are legitimate
fine-tuning targets. The third is a retrieval failure and fine-tuning will not touch it.
The dataset built in Steps 2–3 targets the two behavioral issues only.

---

## Issue 1 — Model overstates or embellishes validated retrieved data

**Recurring across all four days.**

Evidence:
- **Day 11, Q9 (X-ray + Silver deductible):** asserted "X-rays are typically covered for
  preventive care visits at no cost" — no source document contained that. The correct
  $1,500 deductible came from context; the coverage claim did not.
- **Day 12, Variant B, Q3 (physical therapy / Silver):** fabricated a flat denial —
  "The Silver HMO plan does not cover physical therapy" — not present anywhere in context.
- **Day 12, Variant C, Q4 (X-ray + Silver):** claimed the procedure "would be covered as
  preventive care under your plan" and that "you do not need to meet the annual deductible
  because this benefit is excluded from the deductible requirement." Both fabricated.
- **Day 13, Q3, run 2 (physical therapy / Silver):** the `check_coverage` tool returned
  `determination: unknown` with an explicit note that unknown ≠ excluded. The model
  overwrote this with "The Silver HMO plan covers physical therapy." Same input, different
  output between run 1 (honest) and run 2 (fabricated).
- **Day 13, Q2 (claim C1001):** tool returned only status/procedure/amount. Model added
  "you'll be notified by mail once a decision is made" — invented.

**Cause:** the model, when composing a natural-language answer from validated data on
turn 2, adds shape or certainty that the underlying data does not support. This happens
whether the underlying data comes from RAG (Day 11–12) or a Pydantic-validated tool
(Day 13). The upstream layer is working; the composition layer is not faithful.

**Verdict — fine-tunable.** This is a behavior pattern (how the model treats retrieved
context), not a knowledge gap. Training on paired (context, faithful-answer) examples
where the correct behavior is to relay what's there and nothing more is exactly what
fine-tuning is for. Day 13 already proved the tool layer can hand the model an `unknown`
determination; fine-tuning is the layer that teaches the model to keep saying "unknown"
instead of upgrading it.

## Issue 2 — Disclaimer emission is unreliable and format-fragile

**Recurring across Day 11 and Day 13.**

Evidence:
- **Day 11:** the Day 11 system prompt included compliance language ("not medical advice")
  but the disclaimer appeared inconsistently across the 10 test answers — sometimes present,
  sometimes absent, sometimes partial.
- **Day 12 scoring:** Variant C demonstrated the disclaimer in a worked few-shot example
  and Variant D specified it as a rule; **neither produced it even once** across five
  responses. Variant E made it unconditional and got 5-of-5, but at the cost of the
  disclaimer running ~40 words on every response including short factual ones.
- **Day 13, Q1, run 1:** the model's entire final answer collapsed to the disclaimer alone
  — the $500 premium the tool returned was dropped. Direct test confirmed the tool
  returned the premium reliably; the model satisfied the "append the disclaimer verbatim"
  rule while omitting the answer body. On rerun the answer was correct. Same code, same
  input, different output.

**Cause:** disclaimer behavior is currently prompt-driven, and the prompt has to fight
two failure modes at once — the model forgetting the disclaimer on short answers, and the
model returning *only* the disclaimer on very short answers. Variant E's unconditional
rule fixed the first but exposed the second. The instructions the model receives at
inference time are not a stable way to hold this line.

**Verdict — fine-tunable.** Emitting a consistent closing disclaimer at the right point
in every response is a format pattern. Training examples where every assistant turn ends
with the disclaimer (and none ever consists *only* of the disclaimer) would encode the
behavior at the weights, and remove the ~40-word verbatim rule that currently inflates
every response.

## Issue 3 — Retrieval misses on structured lookups and specific documents

**Recurring across Day 10, Day 11, and Day 12.**

Evidence:
- **Day 10 SQL bugs:** LLM-generated SQL used case-sensitive comparisons that missed
  matches (`'approved'` vs actual `'Approved'`), confused columns (`coverage_type` vs
  `network_tier`), and over-joined plan-level queries. Rated 5 good / 2 partial / 3 poor
  across the 10-question harness.
- **Day 11, Q8 (enrollment requirements):** the `enrollment.txt` chunk containing the
  actual enrollment information never surfaced in the top-5 vector results, despite being
  the most relevant document in the corpus.
- **Day 12, Q1 (Gold PPO premium):** the retrieved structured context was
  `[{'monthly_premium': 500}]` — the SQL result stripped of its plan label. Four of five
  prompt variants either refused or hedged, not because they were poorly prompted, but
  because the context they were given was uninterpretable.
- **Day 9:** a "Silver plan" query ranked the one true Silver chunk 5th of 5 — the model
  was answering from Gold PPO chunks that semantically dominated. Fixed with metadata
  filtering, but the underlying ranking problem persists for any question without an
  obvious filter.

**Cause:** the model is being handed the wrong information, or handed information with
its context stripped. This is a data-layer problem — SQL generation, vector-store
ranking, chunk formatting, missing exclusions data (Day 6).

**Verdict — NOT fine-tunable.** No amount of behavioral training will help a model answer
a question about a document it never sees, or write correct SQL against a schema it
misremembers. Fine-tuning improves behavior *given the right context*; it cannot conjure
context that isn't there. These issues are called out here specifically so they are not
mistaken for something the Day 14 dataset will address — they belong to a retrieval-layer
day (SQL generation with schema-in-prompt, or a re-tagged knowledge base) that has not
been scheduled yet.

---

## What the Day 14 dataset will teach the model

Given the above, the ~30 training examples curated in Steps 2–3 will encode two
behaviors and only two:

1. **Faithful composition from validated context.** When retrieved context or a tool
   result says something specific, relay it exactly. When it says "unknown" or does not
   address the question, say so — do NOT upgrade to a confident answer. Do NOT add
   details (notification methods, coverage assumptions, next steps) that were not in the
   context or the tool result.

2. **Consistent closing disclaimer at natural length.** Every response ends with the
   standard disclaimer. The disclaimer never stands alone — every response has an answer
   body first. Short answers stay short (2–3 sentences before the disclaimer); the model
   does not pad, but it also does not omit.

### What it will explicitly NOT try to teach

- Which plan has which deductible (that's data — belongs in the DB and in tool responses).
- The claims process wording (that's document text — belongs in the vector store).
- How to route between structured and unstructured lookups (that's the Day 10 classifier).
- Whether a specific procedure is covered (that's the Day 6 knowledge base, which has no
  exclusions data — the tool is honest about this and the model must be too).

Teaching any of those via fine-tuning would risk baking today's specific plan figures into
the weights, making the model wrong the moment those figures change. The rule holds:
**data lives in retrieval; behavior lives in weights.**
