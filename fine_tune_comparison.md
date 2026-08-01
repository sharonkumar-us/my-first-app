# Day 15 — Fine-Tune Comparison

## Setup

**Base model:** `Qwen/Qwen2.5-0.5B-Instruct` (unmodified).
**Fine-tuned:** same base model + a LoRA adapter (r=8, targeting `q_proj` and `v_proj`) trained on `fine_tune_train.jsonl` — 25 examples, 3 epochs, LR 2e-4.
**Held-out test set:** 5 examples from `fine_tune_test.jsonl`, one per behavior category (faithful lookup, honest refusal, unknown-stays-unknown, cost without inventing a price, wrong-plan trap). See `fine_tune_prep_notes.md` for why these five and what fine-tuning was and was not expected to fix.

**Environment note.** Production `qwen2.5-coder:7b` and evaluation targets `llama3.1:8b` were both too large to fine-tune on a 16 GB Mac; a 1.5B attempt trained at ~1.75 hr/step due to swap thrashing and was killed. Qwen2.5-**0.5B** completed 3 epochs in 4:27, so it is the base used here. Inference had to be moved to CPU as well (an MPS `matmul` shape bug fires during generation on this model), so evaluation runtime was ~15 minutes rather than a few minutes on GPU. Absolute quality on either side of the comparison is therefore **capped by the 0.5B base model**, not by our data — this comparison measures the *delta* fine-tuning produced, not production readiness.

## Aggregate scores

| Criterion | Base | Fine-Tuned | Δ |
|---|---|---|---|
| Disclaimer present | 0/5 | 1/5 | +1 |
| Jargon defined on first use | 1/5 | 3/5 | +2 |
| Refuses honestly (when expected) | 1/5 | 2/5 | +1 |
| Length under 150 words | 5/5 | 5/5 | 0 |
| **Overall pass (all four)** | **0/5** | **1/5** | **+1** |

The scorer heuristics are pattern-matched string checks, not semantic evaluation. **The aggregate hides more than it shows** — a per-question read of the actual answers tells a different and more useful story, so what follows is the honest interpretation rather than the scoreline.

## What fine-tuning actually changed

**Format signals shifted — clearly and immediately.** The training corpus has a strong shape: refusals begin with *"I don't have that in your plan records"*, plan terms are followed by plain-language explainers, every answer ends with the specific closing disclaimer. All three of these patterns started appearing in the fine-tuned model's outputs, and did not appear in the base. Q1 uses the exact refusal opener; Q3 emits the disclaimer verbatim; Q4 mentions the plan by name. LoRA on 25 examples reliably transferred *phrasing patterns*.

**Judgment did not shift.** Whether to refuse, when to answer literally, when the retrieved context does or doesn't support a claim — none of that improved. The fine-tune replaced one set of surface behaviors with another set of surface behaviors, and picked the wrong one on 4 of 5 held-out questions.

## Per-question analysis (this is the honest read)

**Q1 — "What copay do I owe under Bronze HMO?"**
Context contained a real copay figure (30%). Base answered correctly. Fine-tuned refused: *"I don't have that in your plan records."* The scorer rewarded the refusal-format string, but this is a substantive regression — the correct answer was available in context and the base model produced it.

**Q2 — "Do I have a copay for preventive visits?"**
Both base and fine-tuned answered "Yes, you have a copay for preventive visits under Plan P102" — asserting coverage detail (a preventive-specific copay) that the context does not confirm. This is exactly the Day 12 Variant B "over-confident on partial context" failure. Fine-tuning did not touch it. Neither model refused, neither emitted the disclaimer.

**Q3 — "Is mental health therapy covered on Gold PPO?"**
Base fabricated a coverage confirmation: *"Yes, mental health therapy is covered on Gold PPO"* — the Day 12 / Day 13 fabrication pattern. Fine-tuned went to the opposite extreme: its entire output was the closing disclaimer, with **zero words of answer body**. That is the Day 12 Q1 disclaimer-only collapse, structurally reproduced. The scorer marked it as fully passing because it hits every literal check; a human reader sees no answer.

**Q4 — "What will a specialist visit cost on Silver HMO?"**
Base gave an incorrectly-constructed dollar figure ("$1350") from confused arithmetic on the deductible and copay. Fine-tuned asserted *"A specialist visit on Silver HMO will cost $1500"* — that is the Silver HMO annual deductible, presented as the visit cost. A different wrong answer, arguably more confident and therefore worse. Both should have said the exact price isn't in records.

**Q5 — "What's my deductible on the Silver plan?"**
The context contained Gold PPO details, not Silver — this is the "wrong-plan trap" case. Both base and fine-tuned confidently asserted *"The deductible on the Silver HMO (P102) plan is $2000"*, which is the Gold PPO deductible read out and mislabelled. Identical failure both sides. Fine-tuning didn't touch it.

## What this means

**Fine-tuning at this scale is a style transfer tool, not a reasoning tool.** 25 examples were enough to teach a 0.5B model *what a compliant answer looks like* — refusal phrasing, closing disclaimer, jargon explanations — but not *when to use each shape*. The model learned to imitate the surface of the training data uniformly rather than to distinguish the six categories the training data was drawn from.

**The Day 14 category breakdown paid off diagnostically, not curatively.** Grouping the 30 pairs by behavior (A–F) made it possible, when reading these results, to say precisely which behaviors did and did not transfer. Format-heavy categories (refusal phrasing, jargon-defining) moved. Judgment-heavy categories (deciding when to refuse, catching wrong-plan context) did not.

**The 0.5B ceiling is real and matters.** Even the base model's "correct" answers on Q1 were terse fragments, not the full explanation the Day 12 prompt targets. A test on a 7B or larger model would likely show a much larger delta because there is more headroom for style training to interact with existing capability. Extrapolating from these results to production models is not directly valid.

## Verdict on fine-tuning vs. more prompt/retrieval work

For the coverage chatbot as designed, **more prompt and retrieval work would produce larger gains than fine-tuning at this scale**, and the failures observed here support that conclusion rather than contradict it:

- **Q2 and Q5 failures are retrieval failures** — the model was given ambiguous or wrong-plan context and answered from it. No amount of behavioral training will fix these; they were flagged in `fine_tune_prep_notes.md` as out of scope for Day 14, and Day 15 confirms it. The Day 10 SQL bugs and Day 6 tagging gaps are still the highest-value fixes.
- **Q4's regression is a retrieval-shape failure** — the fine-tune amplified the model's confidence in bad numbers rather than teaching it to refuse when the price isn't given. Providing structured cost context (as the tool-calling layer on Day 13 already does) would matter more than any amount of tone training.
- **Q1 and Q3's swap** (base got Q1 right and Q3 wrong; fine-tuned got Q1 wrong and Q3 "right" via a disclaimer-only response) suggests the fine-tune shifted a single implicit threshold — how much retrieved context is enough to answer — in the direction of over-refusal. At 0.5B with 25 examples this is the kind of blunt instrument you get; more examples might sharpen it, but retrieval improvements would remove the need to guess in the first place.

**Where fine-tuning still earned its place:** the disclaimer emission on Q3 and the "I don't have that in your plan records" refusal template on Q1 both showed up cleanly and were nowhere in the base. Those are precisely the *format-consistency* failures Day 11 and Day 12 struggled to hold with prompt-only enforcement. For a production build, the right posture is: fine-tune on ~10× more examples (~250-300) to lock these format guarantees at the weights, then invest most remaining effort in retrieval and tool-use reliability where the substantive wins are.

## Scoring methodology limitations (for the record)

The four heuristics used to produce the aggregate scores are string-pattern checks:

- `disclaimer_present`: does the answer contain the fragment "not medical or legal advice"?
- `defines_jargon`: if the answer uses "deductible" / "copay" / "premium", does an explainer phrase appear nearby?
- `refuses_honestly`: on cases where the ideal answer is a refusal, does the answer contain a refusal marker?
- `length_ok`: is the answer body under 150 words?

None of these check whether the answer is *correct*. Q3's fine-tuned response — the disclaimer alone, with no answer — passes all four. Q1's fine-tuned refusal on a question with a real answer *passes* the "refuses_honestly" check because the base was scored as failing to refuse (correct, it answered), while the fine-tune's inappropriate refusal was scored as refusing well. In a production evaluation the scorer would need semantic comparison (e.g., LLM-graded against the expected answer), which is out of scope for this exercise but should be flagged before any real production decision leans on these numbers.

## Side-by-side scoring on portal criteria (Step 5)

The portal specifies four scoring dimensions for the comparison: **tone**,
**correctness**, **disclaimer usage**, and **terminology clarity**. Each answer
is scored 1 (poor) to 5 (excellent) on each. The heuristic scorer used earlier
in this file measured different axes (disclaimer + jargon + refusal marker +
length) and is retained above for reproducibility; this section is the
human-graded read against the exact criteria the mission asks for.

### Per-question scores (1 = poor, 5 = excellent)

| # | Question | Model | Tone | Correctness | Disclaimer | Terminology |
|---|---|---|---|---|---|---|
| 1 | Bronze HMO copay | Base | 2 | **5** | 1 | 2 |
| 1 | Bronze HMO copay | Fine-tuned | 3 | **1** | 1 | 3 |
| 2 | Preventive-visit copay | Base | 2 | 2 | 1 | 2 |
| 2 | Preventive-visit copay | Fine-tuned | 2 | 2 | 1 | 2 |
| 3 | Mental-health coverage / Gold | Base | 2 | **1** | 1 | 2 |
| 3 | Mental-health coverage / Gold | Fine-tuned | 3 | **1** | **5** | 3 |
| 4 | Specialist cost / Silver | Base | 2 | **1** | 1 | 1 |
| 4 | Specialist cost / Silver | Fine-tuned | 3 | **1** | 1 | 3 |
| 5 | Silver deductible (wrong-plan trap) | Base | 2 | **1** | 1 | 2 |
| 5 | Silver deductible (wrong-plan trap) | Fine-tuned | 2 | **1** | 1 | 2 |

### Averages across the 5 held-out questions

| Dimension | Base avg | Fine-Tuned avg | Δ |
|---|---|---|---|
| Tone | 2.0 | 2.6 | **+0.6** |
| **Correctness** | **2.0** | **1.2** | **−0.8** |
| Disclaimer usage | 1.0 | 1.8 | **+0.8** |
| Terminology clarity | 1.8 | 2.5 | **+0.7** |

### Reading the scores honestly

**Three dimensions moved in the intended direction; one regressed, and it is the
one that matters most.** Fine-tuning made the model warmer, more consistent
about the closing disclaimer, and cleaner in how it introduces plan
terminology. It also made it *less correct* — a −0.8 drop on a 1–5 scale is
substantial, and it comes from the same phenomenon documented in the per-question
analysis above: the fine-tune shifted the model toward refusal *phrasing* and
disclaimer *format* without teaching it *when* to use them. Q1 refused a
question with a real answer in context; Q3 responded with the disclaimer alone
and zero answer body; Q4 stated a wrong number as if it were an estimate.

**None of these is a Day 14 dataset failure.** The training examples all model
the correct behavior on their category. The 0.5B model does not have the capacity
to internalize *which category a new question falls into* from only 25 examples,
so it defaults to the most frequent surface pattern in training (refusals with
disclaimers). Scale — more examples per category, or a larger base model, or
both — is the honest fix.

**Format guarantees are real and worth keeping.** The +0.8 on disclaimer usage
and +0.7 on terminology clarity address exactly the failure modes Day 11 and
Day 12 struggled to hold with prompt-only enforcement (see the Day 12 Variant
comparison in `prompt_variants.md`, where Variants C and D failed to emit the
disclaimer even when instructed). LoRA held those patterns at the weights, which
prompting could not.

### Overall verdict against the portal question

**"Does fine-tuning beat more prompt/retrieval work?"** — no, not at this scale,
and the correctness regression makes the answer clearer than the aggregate
across the four dimensions suggests. For this project, the highest-value next
work is retrieval-side (Day 10 SQL bugs, Day 6 exclusions tagging, Day 12 Q1
context labelling), followed by more training data at ~10× scale to lock format
guarantees without losing correctness. Fine-tuning alone, at the size actually
runnable on this hardware, is a style tool — useful, but not a substitute for
the substance work still outstanding.

## Conclusion

**Did fine-tuning meaningfully improve consistency?** Partially. It reliably
transferred format patterns — closing disclaimer, refusal phrasing,
plan-terminology phrasing — that prompt-only enforcement had failed to hold
across Days 11 and 12. On those axes the +0.6 to +0.8 gains are real. But it
did not improve *correctness*: the fine-tuned model over-applied the same
format patterns to questions where they were wrong, dropping the correctness
score from 2.0 to 1.2. Format consistency improved; answer-quality consistency
did not.

**Or would more prompt/retrieval work have gotten there for less effort?** Yes,
for this project and at this scale. Three of the five held-out failures are
retrieval-shape problems: Q2 answered from ambiguous context, Q4 got confused
math instead of an "exact price not in records" refusal, Q5 read Gold PPO
numbers as if they were Silver's. None of these are behaviors fine-tuning can
fix; they need the retrieval-layer work already flagged in
`fine_tune_prep_notes.md` — Day 10's SQL bugs, Day 6's exclusions tagging, and
Day 12's context labelling.

Fine-tuning at ~250-300 examples on a larger base model would likely be worth
doing later, specifically to lock the format guarantees. But as a substitute
for the retrieval work still outstanding, it is the wrong tool.

## Files produced today

- `train_fine_tune.py` — training script (Qwen 0.5B + LoRA, 3 epochs, MPS)
- `evaluate_fine_tune.py` — before/after generator + heuristic scorer (CPU)
- `adapters/` — the trained LoRA weights (~5MB, not committed per repo layout guidance)
- `fine_tune_comparison.md` — this file, and the raw per-question outputs
