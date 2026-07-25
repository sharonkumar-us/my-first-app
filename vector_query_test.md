# Vector Query Test — Day 9

## Setup

- Collection: `coverage_kb` (Chroma, persistent client, `./chroma_data`)
- Records upserted: 16
- `collection.count()` verified: 16
- Embedding model: `all-MiniLM-L6-v2` (same model used for both stored chunks and the query — required for meaningful similarity comparison)

## Test Query

**Query:** "Is physical therapy covered under the Silver plan?"

**Method:** `collection.query(query_embeddings=[...], n_results=5)`

## Results

| Rank | id | distance | section | plan_type | text (truncated) |
|---|---|---|---|---|---|
| 1 | `raw_text/benefits.txt::chunk1` | 0.9582 | coverage | (none) | "...describes the Gold PPO plan, a fictional health plan..." |
| 2 | `raw_text/benefits.txt::chunk2` | 0.9613 | coverage | (none) | "The Gold PPO plan covers preventive care visits..." |
| 3 | `raw_text/claims_process.txt::chunk8` | 1.1979 | coverage | (none) | "The claim is checked against the member's plan coverage rules..." |
| 4 | `raw_text/claims_process.txt::chunk10` | 1.2253 | coverage | (none) | "Member Jane Test... claim for an X-ray procedure... Gold PPO plan..." |
| 5 | `plan::P102` | 1.2314 | coverage | P102 | "Silver HMO (P102): $300/month premium, $1500 annual deductible..." |

## Review

**Are they relevant?** Partially. All 5 results are coverage-related, so the embedding model correctly identified the general topic (insurance coverage). However, none directly answer the question, because our synthetic knowledge base never actually contains any content about physical therapy specifically — this is a genuine gap in source data, not a retrieval bug.

**Do they reflect Silver-plan-specific coverage?** No — this is the key finding. The single Silver HMO plan chunk (`plan::P102`) that should be the most directly relevant result instead ranked **last** (5th of 5). The top 4 results are about the **Gold PPO** plan or generic claims process text, not Silver at all.

## Retrieval miss — root cause

Vector similarity search ranks by overall semantic closeness across the whole query, not by exact keyword or entity matching. The query mentions both "physical therapy" (a coverage topic) and "Silver plan" (a specific entity) — but since none of our chunks mention physical therapy, and multiple chunks share general coverage/plan language, the model weighted the broader "coverage plan" semantic pattern more heavily than the specific word "Silver." A chunk about the Gold PPO plan's covered services ended up "closer" in embedding space than the chunk that actually names the Silver plan, simply because the Gold PPO chunk uses more coverage-related vocabulary overall.

**Implication for a real chatbot:** pure semantic search isn't enough when a query needs to be scoped to one specific entity (like "my plan"). A production system would likely need **metadata filtering** (e.g., `where={"plan_type": "P102"}`) to restrict the search to only Silver plan chunks *before* ranking by similarity — rather than relying on semantic similarity alone to surface the right plan among several.
