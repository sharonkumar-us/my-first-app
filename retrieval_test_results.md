# Retrieval / Matching Engine — Test Results (Day 10)

## Setup

- `retrieval_engine.py` implements `classify_question()`, `sql_lookup()`, `vector_lookup()`, and `retrieve()` (the router that merges both).
- Classifier: prompt-based, using local Ollama (`qwen2.5-coder:7b`) — not keyword rules.
- SQL generation: **LLM-generated** (not template-based) — the model is given the `plans`/`claims` schema and writes its own `SELECT` statements, with a guard that refuses anything that isn't a `SELECT`.
- 10-question test harness run against the live pipeline (`coverage.db` + `coverage_kb`).

## Results Summary

| # | Question | Classification | Score | Notes |
|---|---|---|---|---|
| 1 | What's my copay under the Bronze HMO plan? | structured | **Poor** | LLM wrote an unneeded JOIN to `claims` requiring an `'approved'` claim (copay is plan-level, no join needed) + used lowercase `'approved'` vs actual `'Approved'` — case-sensitive mismatch. Real answer (30%) never surfaced. |
| 2 | Is maternity care covered on the Bronze plan? | both | **Partial** | SQL used `plan_name = 'Bronze'` instead of `'Bronze HMO'` — wrong value, but coincidentally still correct-ish since no maternity content exists anywhere in our data (known Day 6 gap). Vector search did correctly retrieve the Bronze HMO plan chunk. |
| 3 | What's the status of claim C1001? | structured | **Good** | Correct: `Pending`. |
| 4 | Is physical therapy covered under my Silver plan? | both | **Partial** | SQL filtered on `coverage_type = 'Silver'`, but `coverage_type` actually stores `PPO`/`HMO` — tier names live in `network_tier` instead. Wrong column, not just wrong value. Result (`0`) is directionally fine only because no physical therapy claims exist at all. Vector search correctly ranked the Silver HMO chunk this time. |
| 5 | What's the monthly premium for Gold PPO? | structured | **Good** | Correct: $500. |
| 6 | What is the claims submission process? | unstructured | **Good** | Relevant claims-process chunks retrieved correctly. |
| 7 | How much was billed for claim C1003? | structured | **Good** | Correct: $150. |
| 8 | What information is needed to enroll in a plan? | unstructured | **Poor** | The actual most-relevant document (`raw_text/enrollment.txt`, which lists the real required fields) never appeared in the top-5 results. Generic "contact Member Services" content surfaced instead — a genuine retrieval miss, not a data gap. |
| 9 | Is my X-ray procedure covered and what's my deductible under Silver HMO? | both | **Poor** | SQL required `status = 'approved'` (wrong case) on a claim that's actually `Denied` — but the deductible is a plan-level fact and shouldn't have needed any claim-status filter at all. A real, answerable fact ($1500 deductible) got excluded by unnecessary logic. Vector search partially recovered the deductible value as unstructured text, but not reliably. |
| 10 | What's the status of claim C-2031? | structured | **Good** | Correctly returned empty for a claim ID that genuinely doesn't exist — proper edge-case handling. |

**Score: 5 good / 2 partial / 3 poor**

## Key Findings

**1. LLM-generated SQL is powerful but inconsistent on two specific failure modes:**
- **Case-sensitivity mismatches**: the model repeatedly generated `status = 'approved'` (lowercase) when the actual stored value is `'Approved'` (capitalized). This alone caused 2 of the 3 "poor" results (Q1, Q9).
- **Column confusion**: in Q4, the model filtered on `coverage_type` (which stores PPO/HMO) when it should have used `network_tier` (which stores Gold/Silver/Bronze) — a plausible-looking but wrong column guess.
- **Over-joining**: in Q1, the model added an unnecessary join to `claims` to answer a question that only needed the `plans` table — introducing a false dependency on claim status/existence for a fact that's actually claim-independent.

**2. Vector search sometimes compensates for SQL failures, sometimes doesn't:**
- In Q2 and Q4, vector search correctly surfaced the relevant plan chunk even though the SQL logic was flawed — the "both" classification's merged context provided a safety net.
- In Q8, vector search failed entirely — the single most relevant document was never retrieved, with no structured-data fallback to compensate (since the question was classified purely `unstructured`).

**3. Edge-case handling for nonexistent data is a genuine strength (Q10):** the pipeline correctly returns empty results rather than fabricating an answer when a claim ID doesn't exist — this is a good sign for downstream LLM answer generation, since an empty context should prompt an honest "no data found" response rather than a hallucinated one.

## Baseline for Day 11

This 5/2/3 split is the honest starting point going into Day 11's context/prompt work. The two most actionable fixes surfaced today:
1. **Normalize case sensitivity** in generated SQL (e.g., use `LOWER(status) = 'approved'` in the schema prompt, or normalize the LLM's output before execution) to eliminate the Q1/Q9 failure mode.
2. **Investigate why `enrollment.txt`'s chunks rank outside top-5** for a directly relevant enrollment question (Q8) — this may tie back to the Day 6 section-classification gap, where enrollment-tagged content is thin (only 1 chunk in the whole knowledge base) and may not be embedding distinctly enough to rank well.
