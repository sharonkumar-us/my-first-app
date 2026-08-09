# Day 19 Step 6 — Rich Outputs Test

Three questions tested live against the full stack (Streamlit → FastAPI → RAG pipeline + card builder), confirming citations, claim status cards, and coverage summary cards all render correctly and persist across conversation turns.

## Test 1 — Policy citations (vector question)

**Question:** "What is the claims submission process?"

**Result:** PASS

- Answer generated correctly from `raw_text/claims_process.txt`
- "Policy sources (5)" expander rendered under the answer, listing chunk6, chunk5, chunk7, chunk8, chunk10 from `claims_process.txt`
- Confirmed citations persist across a second turn (expander remained visible after sending a follow-up message) — this was the Step 2 bug fix, verified working

## Test 2 — Claim status card (tool-style lookup)

**Question:** "What's the status of claim C1001?"

**Result:** PASS

- Text answer: "The current status of your claim C1001 is 'pending.'..."
- `ClaimStatusCard` rendered as a bordered container: Claim C1001, Status: Pending, Amount: $250
- Card correctly built via direct DB lookup (`get_claim_status`) triggered by claim-ID pattern match in the message, independent of the RAG text answer
- Card persisted across the next turn (verified after asking a follow-up plan question)

## Test 3 — Coverage summary card (plan lookup)

**Question:** "What's the deductible on the Gold PPO plan?"

**Result:** PASS (card) / initially FAILED (text answer) — root cause found and fixed

- `CoverageSummaryCard` rendered correctly: Gold PPO, Deductible: $2,000, Copay: 10.0%
- **However**, the text answer initially said "I don't have that in your plan records" — contradicting the card. Root cause: the Day 10 SQL-generation prompt did not require `plan_name` in the SELECT list, so a bare `annual_deductible: 2000` reached the grounding model with no plan attached, and it correctly refused to guess which plan it belonged to.
- **Fix applied** in `retrieval_engine.py`:
  - `generate_sql()` prompt now requires identifying columns (`plan_name`/`plan_id` for plans, `claim_id`/`plan_id` for claims) in every query
  - Added known `plan_name` and `status` values to the schema context, fixing a separate case-sensitivity bug (`'approved'` vs `'Approved'`) and an over-joining pattern for single-table questions
  - SQL result rows are now formatted as labeled `key: value` text instead of a raw Python dict repr, for clearer parsing by the grounding model
- Re-tested after the fix: `retrieve()` returned `plan_name: Gold PPO, annual_deductible: 2000` — self-labeled, resolving the contradiction
- Full before/after evidence: 10-question test harness re-run in `retrieval_engine.py`'s `__main__` block; Q1 (previously returning empty rows due to an invented join) now correctly returns `plan_name: Bronze HMO, copay_pct: 30`

## Summary

| # | Test | Citations | Card | Text Answer | Notes |
|---|------|-----------|------|--------------|-------|
| 1 | Claims submission process | ✅ | — | ✅ | Citations persist across turns (Step 2 fix verified) |
| 2 | Claim C1001 status | — | ✅ | ✅ | Card + text agree |
| 3 | Gold PPO deductible | — | ✅ | ✅ (after fix) | Longstanding Day 10 SQL plan-label bug fixed during this session |

**Known remaining gaps (not addressed in this session, tracked separately):**
- Some structured queries still return empty rows when the underlying claims data doesn't have a matching row (e.g. no "maternity care" or "physical therapy" claims exist in the synthetic dataset) — this is a data-sparsity limitation, not a query bug, and the vector fallback (`classification: both`) still supplies policy text in these cases.
- Day 13 Q3 nondeterminism (`unknown` → "covered" on turn 2) — unchanged, not investigated this session.
- Day 11 `enrollment.txt` chunk not surfacing in top-5 vector results — unchanged, not investigated this session.
