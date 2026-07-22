# Knowledge Base — Sanity Check Notes (Day 6)

## Summary

- **Total records:** 16
- **Sources:** 3 plan rows from `coverage.db` (structured), 13 text chunks from `raw_text/*.txt` (unstructured)
- **Section distribution:** `coverage: 13`, `claims: 2`, `enrollment: 1`, `exclusions: 0`

## Manual review (5 random chunks)

All 5 sampled chunks were coherent — no mid-sentence cuts, each chunk represents a complete thought. Confirmed both plan-summary sentences (structured) and policy-text chunks (unstructured) read cleanly on their own.

## Known gaps

**1. No exclusions chunks (0 records)**
Our synthetic `benefits.pdf` never included an exclusions clause, so there's nothing in the knowledge base tagged `section: exclusions`. This is a source-data gap, not a pipeline bug — the mapping logic supports this category, it just has nothing to classify into it yet. Worth adding a synthetic exclusions section to a future benefits document if this needs testing.

**2. Section classification is header-based, not content-based**
`map_section()` looks at each chunk's *detected header* (e.g., "Overview," "Example (Fictional)") for keywords like "claim" or "enroll" — it doesn't inspect the chunk's actual text. This means content that's clearly about claims (e.g., the walk-through example under a header like "Example (Fictional)") can get bucketed under the generic `coverage` section instead of `claims`, simply because the header itself doesn't contain the word "claim."

**Impact:** minor — most content is still reasonably categorized, and nothing is lost (it's all still in the knowledge base, just under a broader section tag). A future improvement would be content-based classification (e.g., checking the chunk text itself, or using a small classifier) rather than relying solely on the section header.
