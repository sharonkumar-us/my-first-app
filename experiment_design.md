# Day 26 Step 5 — Experiment Design: Variant A vs. Variant E

## Background and why these two variants

Auditing prompt_variants.md for this experiment revealed it is incomplete:
it contains only Variant A's full text and an entirely unscored results
table (all cells blank) -- Variants B through E were never written into
this file, and Variant A's row was never filled in, despite rag_chatbot.py
citing this file as the source for the Day 12 "Variant E won 15/20"
decision. This is a genuine documentation gap, not something fabricated
for this exercise.

This means Variant A vs. Variant E (the current PRODUCTION_SYSTEM_PROMPT in
rag_chatbot.py) is not a re-run of an already-known result -- it is a
comparison that was apparently designed but never actually completed. Both
prompts' full text is real and available (Variant A from prompt_variants.md,
Variant E from rag_chatbot.py), so this experiment answers a real,
previously-open question rather than fabricating a synthetic comparison.

## Variants

**Variant A ("Strict/Formal"):** maximum precision and compliance safety.
Refuses anything resembling medical advice outright, quotes exact values
verbatim, no conversational warmth, declarative sentences only.

**Variant E ("Hybrid," current production prompt):** balances accuracy with
warmth ("Be accurate first and warm second — but be both"), includes a
silent pre-answer check, explains terms in plain language alongside the
raw figure, and redirects medical questions rather than refusing outright.

## Hypothesis

Variant E will score higher than Variant A on member-facing answer quality
(tone, plain-language clarity) while performing comparably on accuracy and
compliance, since both variants share the same core grounding discipline
(context-only answers, no fabrication) — the difference is expected to be
in HOW the correct information is communicated, not WHETHER it's correct.

Variant A is expected to score higher specifically on strict compliance
edge cases (a member pushing for something resembling medical advice),
since it refuses more categorically than Variant E's softer redirect.

## Metric

Percent of the 15 answers rated "good" per variant, scored across four
sub-criteria (each answer gets a pass/fail on each, "good" = passes all
four):
- **Accuracy** — matches the actual data (plan_name, deductible, premium,
  claim status, etc. verified against coverage.db / retrieved context)
- **Tone** — appropriate warmth without being unprofessional; not cold or
  robotic, not overly casual
- **Conciseness** — answers the question without unnecessary padding
- **Compliance** — includes the required disclaimer, does not give medical
  advice, does not overstate an "unknown" coverage determination as
  "covered"

## Sample size

15 questions, spanning the same categories used in Day 19-24 testing
(claim status, plan terms, coverage determination, general process,
off-topic/edge cases) — reusing established, already-validated question
categories rather than inventing a new question set, so results are
comparable to this project's prior findings (e.g. the Day 12
"unknown -> covered" looseness documented across Days 21-25).

## Decision rule

- If Variant E's "good" rate is at least 10 percentage points higher than
  Variant A's (i.e. at least 1.5 more of 15 questions scored fully good),
  Variant E is confirmed as the better default and stays in production —
  consistent with, and now actually evidenced for, the Day 12 decision.
- If Variant A scores at least 10 percentage points higher, that is a
  genuine reversal worth investigating further before changing production.
- If the two are within 10 percentage points of each other (i.e. differ by
  1 question of 15 or less), the difference is NOT considered meaningful at
  this sample size — 15 questions is too small to distinguish a real
  effect from noise at that margin, and the result should be reported as
  "no clear winner" rather than forcing a conclusion.

This decision rule is deliberately conservative given the small sample:
a 15-question test can distinguish a large effect but should not be
over-interpreted as proving a small one either way.
