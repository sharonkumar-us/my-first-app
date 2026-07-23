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

---

# Embeddings — Sanity Check Notes (Day 7)

## Summary

- **Model:** `all-MiniLM-L6-v2` (sentence-transformers, free/local)
- **Embedding shape:** `(16, 384)` — 16 chunks, 384 dimensions each
- **Deliverables:** `embeddings.npy` (raw vectors), `embeddings_2d.png` (PCA scatter plot)

## Cluster sanity check

The PCA scatter plot shows the `coverage` section (13 of 16 chunks) forming the bulk of the plot, with points at varying distances from each other — expected, since "coverage" is a broad catch-all bucket covering several different sub-topics (overview, covered services, member support, plan summaries), not one narrow theme.

**Limitation:** the `claims` section only has 2 chunks, and they land far apart from each other in the plot (no visible clustering). With just 2 points, this isn't a meaningful test of "do same-section chunks cluster" — and it's compounded by the known Day 6 gap where several genuinely claims-related chunks (e.g. the walkthrough example) were mis-tagged as `coverage` instead of `claims` by the header-based classifier. This shrinks the `claims` category down to too few, likely unrelated, points to draw a real conclusion from.

**Impact:** the embeddings pipeline itself ran correctly (correct shapes, successful PCA reduction, plot generated) — this is a data-volume and metadata-tagging limitation, not a bug in the embedding step. A meaningful cluster validation would need either more chunks per section, or fixing the Day 6 section-classification gap first so `claims` accurately reflects all claims-related content.
