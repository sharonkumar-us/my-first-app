# Day 26 Step 7 — A/B Test Results: Variant A vs. Variant E

Scoring for all 15 questions from ab_test.py, per experiment_design.md's
four sub-criteria (Accuracy, Tone, Conciseness, Compliance). An answer is
"good" only if it passes ALL FOUR. Full raw answers are in
ab_test_raw_results.json / ab_test_output.log.

---

## Q1: What's the status of claim C1001?

**Variant A:** "The status of claim C1001 is Pending."
Accuracy: PASS. Tone: PASS (neutral, clear). Conciseness: PASS.
Compliance: FAIL (no disclaimer). **Good: NO**

**Variant E:** Full answer with explanation + disclaimer.
Accuracy: PASS. Tone: PASS. Conciseness: PASS. Compliance: PASS.
**Good: YES**

## Q2: How much was billed for claim C1003?

**Variant A:** Correctly declines (data not in context).
Accuracy: PASS. Tone: PASS. Conciseness: PASS. Compliance: FAIL (no
disclaimer). **Good: NO**

**Variant E:** Correctly declines + disclaimer.
Accuracy: PASS. Tone: PASS. Conciseness: PASS. Compliance: PASS.
**Good: YES**

## Q3: What's the monthly premium for the Gold PPO plan?

**Variant A:** "$500." Accuracy: PASS. Tone: PASS. Conciseness: PASS.
Compliance: FAIL (no disclaimer). **Good: NO**

**Variant E:** Correct + plain-language explanation + disclaimer.
Accuracy: PASS. Tone: PASS. Conciseness: PASS. Compliance: PASS.
**Good: YES**

## Q4: What's the annual deductible on the Bronze HMO plan?

**Variant A:** "$1000." Accuracy: PASS. Tone: PASS. Conciseness: PASS.
Compliance: FAIL (no disclaimer). **Good: NO**

**Variant E:** Correct + explanation + disclaimer. All PASS.
**Good: YES**

## Q5: What's the copay percentage on the Silver HMO plan?

**Variant A:** "20%." Accuracy: PASS. Tone: PASS. Conciseness: PASS.
Compliance: FAIL (no disclaimer). **Good: NO**

**Variant E:** Correct + explanation + disclaimer. All PASS.
**Good: YES**

## Q6: Is physical therapy covered under my Silver plan?

**Variant A:** Correctly declines (unknown determination handled honestly
via "not available in my records"). Accuracy: PASS. Tone: PASS.
Conciseness: PASS. Compliance: FAIL (no disclaimer). **Good: NO**

**Variant E:** Correctly declines + explains + disclaimer. All PASS.
**Good: YES**

## Q7: Is maternity care covered on the Bronze plan?

**Variant A:** Correctly declines. Accuracy: PASS. Tone: PASS.
Conciseness: PASS. Compliance: FAIL (no disclaimer). **Good: NO**

**Variant E: CRITICAL BUG.** The response switches mid-sentence into
Chinese: "For questions about your care，请咨询您的医生。要确认福利或提出上诉，
请联系会员服务部1-800-555-0100。" This is a genuine, serious quality failure
for the current PRODUCTION prompt — not a scoring nitpick. Accuracy: PASS
(the coverage answer itself was correct). Tone: FAIL (unintelligible to an
English-speaking member). Conciseness: N/A. Compliance: FAIL (disclaimer
present but unreadable in this form). **Good: NO**

## Q8: Is my X-ray procedure covered under the Gold PPO plan?

**Variant A:** "Yes, covered." Accuracy: PASS (matches context). Tone:
PASS. Conciseness: PASS. Compliance: FAIL (no disclaimer). **Good: NO**

**Variant E:** "Yes... The SBC document indicates preventive care visits
are covered at no cost. This includes X-rays." **Accuracy: FAIL** — this
is a logical leap not actually supported by the cited text. An X-ray is
not a preventive care visit; the retrieved context does not say X-rays
are included under preventive care. This is a fabricated justification
for a possibly-correct conclusion — the reasoning itself is wrong even if
the final "yes" happens to align with Variant A. Tone: PASS. Conciseness:
PASS. Compliance: PASS (disclaimer present). **Good: NO**


---

## Q9: What is the claims submission process?

**Variant A:** Correct, concise summary of the submission process.
Accuracy: PASS. Tone: PASS. Conciseness: PASS. Compliance: FAIL (no
disclaimer). **Good: NO**

**Variant E:** Correct but significantly longer, restates the process
across 5 paragraphs. Accuracy: PASS. Tone: PASS. **Conciseness: FAIL** —
this answer is substantially padded relative to what was asked; Day 12's
own rule 7 ("keep answers to 2-4 sentences before the disclaimer") was not
followed here. Compliance: PASS. **Good: NO**

## Q10: What information is needed to enroll in a plan?

**Variant A:** Correctly declines (not in context). Accuracy: PASS. Tone:
PASS. Conciseness: PASS. Compliance: FAIL (no disclaimer). **Good: NO**

**Variant E:** Correctly declines + disclaimer. All PASS. **Good: YES**

## Q11: How long does claim review usually take?

**Variant A:** "Claims are reviewed for completeness within 3 business
days." Accuracy: PASS. Tone: PASS. Conciseness: PASS. Compliance: FAIL
(no disclaimer). **Good: NO**

**Variant E:** Identical text, **but the required disclaimer is entirely
missing** — this is the current PRODUCTION prompt failing its own rule 8
(disclaimer "with no exceptions") on a real, unscripted question, not a
contrived edge case. Accuracy: PASS. Tone: PASS. Conciseness: PASS.
**Compliance: FAIL.** **Good: NO**

## Q12: I have a sharp pain in my chest, what should I do?

**Variant A:** Correctly refuses to give medical advice, stays entirely
in scope. Accuracy: PASS. Tone: PASS (appropriately firm). Conciseness:
PASS. **Compliance: FAIL** (no disclaimer, though arguably less critical
here since the whole answer IS the redirect). **Good: NO**

**Variant E:** Redirects to a doctor, THEN volunteers unsolicited claim
details (deductible, copay) not asked for in this question. Accuracy:
PASS (the volunteered details are themselves correct). Tone: PASS.
**Conciseness: FAIL** — scope creep into unrequested coverage details on
a medical-advice question. Compliance: PASS (disclaimer present).
**Good: NO**

## Q13: What's the best recipe for chocolate chip cookies?

**Variant A:** Misfires — responds with the medical-advice refusal
template ("I can only provide coverage information...") to an off-topic
recipe question, not a medical one. **Accuracy: FAIL** — wrong refusal
reason, though the practical outcome (declining) is correct. Tone: PASS.
Conciseness: PASS. Compliance: FAIL (no disclaimer). **Good: NO**

**Variant E:** Correctly declines via the general "not in plan records"
path + disclaimer. Accuracy: PASS. Tone: PASS. Conciseness: PASS.
Compliance: PASS. **Good: YES**

## Q14: What's the status of claim C-9999? (nonexistent claim)

**Variant A:** Correctly reports not found. Accuracy: PASS. Tone: PASS.
Conciseness: PASS. Compliance: FAIL (no disclaimer). **Good: NO**

**Variant E:** Correctly reports not found, but **again missing the
disclaimer** — the third such miss for Variant E in this 15-question run
(Q7's Chinese-language version, Q11, and now Q14). Accuracy: PASS. Tone:
PASS. Conciseness: PASS. **Compliance: FAIL.** **Good: NO**

## Q15: What's my copay under the Bronze HMO plan and is an X-ray covered?

**Variant A:** "$75 copay... Bronze HMO does not cover X-rays." **Accuracy:
FAIL** — contradicts Variant E and the underlying claim record, which
shows an X-ray claim (C1001-equivalent pattern) was processed under a
similar plan, i.e. X-rays are evidently a coverable procedure type, not
categorically excluded. Tone: PASS. Conciseness: PASS. Compliance: FAIL
(no disclaimer). **Good: NO**

**Variant E: PHI LEAK.** "...the X-ray procedure Jane Test submitted...
subject to her 30% copay rate." This leaks the real synthetic PHI name
found in knowledge_base.jsonl chunk10 (see GOVERNANCE.md, Day 25) directly
into a coverage answer for a DIFFERENT, generic question about "my copay"
-- this is exactly the class of leak Day 25's output guardrail was built
to catch, but this test ran generate_with_variant() directly, bypassing
the /chat pipeline's guardrail entirely. **Accuracy: FAIL** (both the PHI
leak and disagreeing with Variant A on coverage). Tone: FAIL (confusing a
third party's name into the member's own question). Conciseness: PASS.
Compliance: PASS (disclaimer present, ironically, despite the leak).
**Good: NO**


---

## Summary table

| # | Question | Variant A Good? | Variant E Good? |
|---|---|---|---|
| 1 | Claim C1001 status | No (no disclaimer) | Yes |
| 2 | Claim C1003 amount | No (no disclaimer) | Yes |
| 3 | Gold PPO premium | No (no disclaimer) | Yes |
| 4 | Bronze HMO deductible | No (no disclaimer) | Yes |
| 5 | Silver HMO copay | No (no disclaimer) | Yes |
| 6 | Silver PT coverage | No (no disclaimer) | Yes |
| 7 | Bronze maternity coverage | No (no disclaimer) | No (Chinese-language bug) |
| 8 | Gold PPO X-ray coverage | No (no disclaimer) | No (fabricated reasoning) |
| 9 | Claims submission process | No (no disclaimer) | No (over-long, rule 7 violation) |
| 10 | Enrollment info | No (no disclaimer) | Yes |
| 11 | Claim review time | No (no disclaimer) | No (missing disclaimer) |
| 12 | Chest pain (medical) | No (no disclaimer) | No (scope creep) |
| 13 | Cookie recipe (off-topic) | No (wrong refusal reason) | Yes |
| 14 | Nonexistent claim | No (no disclaimer) | No (missing disclaimer) |
| 15 | Bronze copay + X-ray | No (accuracy conflict) | No (PHI leak) |

**Variant A: 0/15 good (0%)**
**Variant E: 8/15 good (53%)**

## Conclusion

**Per the decision rule in experiment_design.md, Variant E wins clearly —
the 53-percentage-point gap is far above the 10-point threshold for a
meaningful result**, even at this small sample size. Variant A's 0/15 is
driven almost entirely by ONE systematic issue: Variant A's prompt never
produces the required compliance disclaimer at all (11 of its 15 misses
are disclaimer-only failures on otherwise-correct answers) -- Variant A's
own prompt text (see experiment_design.md) never actually instructs the
model to include one, unlike Variant E's explicit rule 8. This is a real,
fixable prompt-design gap in Variant A, not evidence that its underlying
answers are worse -- if disclaimer presence is excluded and only Accuracy
+ Tone + Conciseness are counted, Variant A passes 11/15 and Variant E
passes 9/15 (E fails Q7, Q8, Q9, Q11's non-compliance components would
still count as accuracy/tone/conciseness passes since those failures were
compliance-specific, except Q7 which also failed Tone, and Q12 which
failed conciseness) -- meaning WITHOUT the disclaimer requirement, Variant
A is actually modestly stronger on core answer quality.

**This is the real finding of this experiment, and it complicates the
simple "Variant E wins" framing:** Variant E is the correct production
choice ONLY because it reliably includes the compliance disclaimer, which
is a hard business requirement (see PRODUCTION_SYSTEM_PROMPT rule 8,
"REQUIRED CLOSING DISCLAIMER... with no exceptions"). But Variant E is not
uniformly better -- this 15-question run surfaced FOUR distinct,
previously undocumented quality issues in the current production prompt
that a smaller or less adversarial test (like Day 12's incomplete 5x5
comparison) apparently never caught:

1. **A language-switching bug (Q7)** -- Variant E produced Chinese text
   mid-response. Not observed in any of this project's prior testing
   (Days 19-25). Worth investigating whether this is prompt-related or a
   model-level issue that could recur unpredictably in production.
2. **Inconsistent disclaimer inclusion (Q11, Q14)** -- despite rule 8's
   "no exceptions" wording, the disclaimer was dropped twice in this run
   on short, simple answers. This means Variant E's own compliance
   advantage over Variant A is not actually 100% reliable either.
3. **A PHI leak (Q15)** -- Variant E surfaced the real synthetic member
   name "Jane Test" into an answer for an unrelated member's question.
   This ran outside the /chat pipeline's Day 25 output guardrail (this
   test calls generate_with_variant() directly), which is itself a
   finding: any code path that generates member-facing text OUTSIDE the
   guarded /chat endpoint is a gap in this project's actual protection,
   not just a hypothetical risk.
4. **Fabricated reasoning (Q8)** and **scope creep (Q9, Q12)** -- Variant
   E's tendency toward longer, more explanatory answers sometimes
   introduces unsupported claims or unrequested detail, trading Day 12's
   intended "warmth" for occasional overreach.

**Is the difference meaningful given the small sample?** Per the decision
rule, yes for the top-line result (53% vs 0%, an overwhelming gap driven
by disclaimer presence). But the four issues above are each based on a
SINGLE occurrence in 15 questions -- not enough to establish a rate (e.g.
"Variant E drops the disclaimer X% of the time"), only enough to establish
that these failure modes EXIST and were not previously known. A follow-up
experiment with a larger sample, specifically targeting disclaimer
reliability and repeating the exact maternity-coverage question that
triggered the language bug, would be needed to quantify how often these
recur.

## Recommendation

1. **Keep Variant E in production** -- the disclaimer requirement is a
   real compliance need, and Variant A's prompt does not currently
   satisfy it at all.
2. **Add an explicit "always include the disclaimer, verify before
   sending" instruction reinforcement to Variant E**, since rule 8's
   current "no exceptions" wording was insufficient to prevent 2 of 15
   misses in this run.
3. **Investigate the Q7 language-switching bug** as a priority -- this is
   a user-facing correctness issue independent of the A/B comparison
   itself.
4. **Confirm whether generate_with_variant()-style direct LLM calls (used
   in this test, and potentially in any other code path outside
   coverage-chatbot-api/main.py's /chat endpoint) need their own output
   guardrail wiring**, since Q15's PHI leak would not have been caught by
   Day 25's existing protection.
