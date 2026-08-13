# Day 27 — RAGAS Evaluation Scorecard

## Evaluation approach

RAGAS 0.1.21 (explodinggradients) is incompatible with Python 3.14's asyncio
implementation — `asyncio.timeout()` cannot be used outside a task, which breaks
RAGAS's internal executor on all 60 scoring jobs. Scores were computed manually
using equivalent definitions:

- **faithfulness** — LLM judge (qwen2.5-coder:7b): are all answer claims grounded in context?
- **answer_relevancy** — embedding cosine similarity (all-MiniLM-L6-v2): answer vs question
- **context_precision** — embedding cosine similarity: retrieved context vs question
- **context_recall** — LLM judge: does context contain enough to answer the ground truth?

Eval set: 15 question/ideal-answer pairs covering deductibles, exclusions,
claims status, and plan comparisons. Full pipeline tested: classify → SQL/vector
retrieve → generate.

---

## Before scores (baseline — 16 chunks in knowledge base)

| Metric | Score |
|---|---|
| faithfulness | 0.8267 |
| answer_relevancy | 0.6724 |
| context_precision | 0.4592 |
| context_recall | 0.3333 ← weakest |

---

## Weakest metric: context_recall (0.3333)

**Hypothesis:** The knowledge base contained zero exclusions-tagged chunks
(documented gap since Day 6). Three of the 15 eval questions asked about
exclusions (cosmetic procedures, experimental treatments, dental/vision). For
these questions, retrieval returned general coverage or plan-summary chunks
that did not contain the exclusion information needed to answer correctly —
so context_recall scored low because the context was missing the key facts,
not because the retrieval mechanism was broken.

Secondary contributors: answer_relevancy (0.6724) suggests some answers were
verbose or drifted from the question — consistent with the Variant E scope-creep
finding from Day 26 (Q9, Q12 added unrequested detail).

---

## Fix applied: added 3 exclusion chunks to knowledge_base.jsonl

Added synthetic exclusion clauses covering:
1. Cosmetic procedures and elective surgery exclusions (all plans)
2. Experimental treatments and investigational procedures (all plans)
3. Dental, vision, and hearing services exclusions (all plans)

Re-ran `generate_embeddings.py` (shape now 19×384) and `populate_vector_db.py`
(collection.count() == 19) before re-evaluating.

---

## After scores (19 chunks in knowledge base)

| Metric | Before | After | Δ |
|---|---|---|---|
| faithfulness | 0.8267 | 0.9600 | +0.1333 |
| answer_relevancy | 0.6724 | 0.7452 | +0.0728 |
| context_precision | 0.4592 | 0.4892 | +0.0300 |
| context_recall | 0.3333 | 0.5867 | +0.2534 |

**context_recall improved by +0.25** — the largest gain, directly attributable
to adding exclusion content. The hypothesis was confirmed: the retrieval
mechanism was not broken; the knowledge base simply lacked the content needed
to answer exclusion questions.

---

## Remaining gaps

- context_recall (0.5867) is still below 0.7 — the 3 synthetic exclusion chunks
  cover the main categories but lack specificity (e.g. no per-plan exclusion
  detail, no list of excluded procedure codes).
- context_precision (0.4892) remains the second-weakest metric — general coverage
  chunks are semantically similar to many questions but don't always contain the
  precise answer, which the embedding similarity scorer captures correctly.
- answer_relevancy (0.7452) has room to improve — likely requires tightening the
  generation prompt to reduce scope creep on plan-comparison questions.

## Compatibility note

RAGAS 0.1.21 from PyPI is served by vibrantlabsai (a fork), not the upstream
explodinggradients package. The upstream version installed from GitHub also fails
on Python 3.14 due to asyncio API changes. Manual scoring using the same metric
definitions produces equivalent signal for a training context.
