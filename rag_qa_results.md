# Day 11 — Full RAG Pipeline Q&A Results

## Q1: What's my copay under the Bronze HMO plan?

**Classification:** structured

**Answer:** To find out what your copay is under the Bronze HMO plan, we would need more specific details about the insurance coverage and benefits for that particular plan. The information provided shows only a general copay percentage of 30%, but this does not break down how much your actual copay might be for a specific type of medical service or provider.

If you have further details such as the name of the Bronze HMO plan, deductibles, and any additional insurance nuances, I'd need that to give you more accurate information. Otherwise, I don't know, and it's recommended that you contact customer support for your insurance company for assistance with this query.

## Q2: Is maternity care covered on the Bronze plan?

**Classification:** both

**Answer:** False

## Q3: What's the status of claim C1001?

**Classification:** structured

**Answer:** Doesn't know. The context only provides a generic status of "Pending" without specific information about claim C1001. The member should contact support for assistance with their query regarding claim C1001's status.

## Q4: Is physical therapy covered under my Silver plan?

**Classification:** both

**Answer:** I don't know and suggest the member contact support.

## Q5: What's the monthly premium for Gold PPO?

**Classification:** structured

**Answer:** I don't have that specific information in the context provided. Please let me know how I can assist you further, and if needed, please contact support for more detailed assistance.

## Q6: What is the claims submission process?

**Classification:** unstructured

**Answer:** Members submit claims through the online portal or by mailing a completed claim form. Each claim must include the member ID, plan ID, date of service, and procedure code. Claims are reviewed for completeness within 3 business days. Incomplete claims are returned to the member with a request for additional information. The claim is then checked against the member's plan coverage rules, including deductible status and network tier.

## Q7: How much was billed for claim C1003?

**Classification:** structured

**Answer:** I believe there might be a misunderstanding. The provided context does not include any information about claim C1003 or its claims amount. I suggest you contact support to provide the correct data and member details for accurate assistance.

## Q8: What information is needed to enroll in a plan?

**Classification:** unstructured

**Answer:** I don't know. The provided context does not contain information on what specific details are required for enrollment in a health plan. Members should contact Member Services at 1-800-555-0100 or visit the member portal for assistance with enrollment inquiries.

## Q9: Is my X-ray procedure covered and what's my deductible under Silver HMO?

**Classification:** both

**Answer:** Under the Silver HMO plan, X-rays are typically covered for preventive care visits at no cost or with a smaller copay as specified in the policy. However, the exact copay amount needs to be checked based on the specific terms of the Silver HMO plan you are currently enrolled in. Your annual deductible under Silver HMO is $1500, which must be met before your plan covers additional expenses at 20% copay. The claim status for Jane Test's X-ray procedure is Pending further review. For precise information, Jane should contact support.

## Q10: What's the status of claim C-2031?

**Classification:** structured

**Answer:** I don't have the ability to check on the status of claims or specific cases outside of this conversation. For assistance with a claim status, I suggest you contact support directly.
---

## Step 6 — Comparison Against the Day 10 Baseline

**Day 10 baseline (retrieval only):** 5 good / 2 partial / 3 poor.
**Day 11 (full pipeline, same 10 questions):** 3 good / 3 partial / 4 poor.

### Are answers correct, well-formed sentences (not raw chunks)?

Mostly yes — 9 of 10 answers are natural sentences rather than dumped context. This is
the clearest gain over Day 10, where `retrieve()` returned raw merged context blocks with
no answer layer on top.

Two exceptions:
- **Q2 ("Is maternity care covered on the Bronze plan?") returned a bare `False`** — a raw
  value passed straight through with no sentence built around it. The only true regression
  on this criterion.
- **Q6 (claims submission process)** is well-formed but close to verbatim recitation of the
  source chunk rather than a synthesized answer. Passes, but only just.

### Do they avoid overstating coverage that isn't clearly confirmed?

Largely yes — this is where the grounding system prompt earned its place. Q3, Q4, Q5, Q7
and Q10 all refused rather than guessed when the retrieved context was empty or wrong.

One real violation:
- **Q9 (X-ray + Silver HMO deductible)** asserts X-rays are "typically covered for
  preventive care visits" — general model knowledge, not retrieved context — and volunteers
  a claim status that wasn't asked about. The correct `$1500` deductible came from context;
  the coverage claim did not.

One softer miss in the other direction:
- **Q8 (enrollment requirements)** declares "I don't know" while simultaneously quoting the
  Member Services number that came from retrieved context — under-stating rather than
  over-stating. This is the known `enrollment.txt` retrieval miss from Day 10 resurfacing.

### Net assessment

Day 11 changed the **failure mode**, not the **failure rate**. Bad retrieval used to
produce wrong or empty context that reached the user unfiltered; it now produces honest
refusals. Retrieval accuracy itself is unchanged.

**Root causes carried forward from Day 10 (still unresolved):**
1. LLM-generated SQL case-sensitivity (