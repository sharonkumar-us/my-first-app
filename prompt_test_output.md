# Day 12 — Step 6: Prompt Variant Comparison

5 test questions x 5 system-prompt variants = 25 responses.

Context was retrieved once per question and reused across all five variants,
so the system prompt is the only variable.


---

## Q1: What's the monthly premium for Gold PPO?

**Classification:** structured

<details>
<summary>Retrieved context (shared by all variants)</summary>


```
[Structured data from database]
[{'monthly_premium': 500}]
```

</details>


### Variant A — Strict/Formal

That information is not available in my records. Please contact Member Services.


### Variant B — Warm/Empathetic

As of my last update, we don't have your specific plan details, but the general detail you requested is that the monthly premium for the Gold PPO option is $500. 

If you'd like more tailored information based on your individual policy, or if there are any other parts of your coverage you're curious about, I’m here to help! Feel free to ask me anything else.


### Variant C — Few-Shot

I don't have coverage details on the Monthly Premium for Gold PPO (P101) in our records. The current plan you've referred to is a different one with a monthly premium of $500, but I don't see details specifically for P101 (Gold PPO). You can check this information through Member Services or visit the company's website for more details on your specific Gold PPO plan.


### Variant D — Chain-of-Thought

Gold PPO has a monthly premium of $500.


### Variant E — Hybrid

I don't have that in your plan records — I can see the monthly premium, but it's for a different plan. The monthly premium is $500 for the [other plan name]. For the Gold PPO, you need to contact Member Services at 1-800-555-0100 to find the specific monthly premium.

This is coverage information based on your plan records, not medical or legal advice.
For questions about your care, please consult your doctor. To confirm benefits or file
an appeal, contact Member Services at 1-800-555-0100.


---

## Q2: What's the status of claim C1001?

**Classification:** structured

<details>
<summary>Retrieved context (shared by all variants)</summary>


```
[Structured data from database]
[{'status': 'Pending'}]
```

</details>


### Variant A — Strict/Formal

The status of claim C1001 is Pending. Please contact Member Services for further updates.


### Variant B — Warm/Empathetic

Claim C1001 is currently pending review. It will be processed as soon as possible, and I'll keep you updated. If you have any other questions or need additional assistance, please don’t hesitate to ask.


### Variant C — Few-Shot

The claim C1001 is currently marked as **pending**. This means we're still reviewing it and will update you once we have a determination. If you have any additional questions or need further assistance, please feel free to ask!


### Variant D — Chain-of-Thought

I'm sorry, but I don't have information on the status of specific claims. Please check with the Claims Department at 1-800-555-0200 for assistance.


### Variant E — Hybrid

Claim C1001 is pending.

This is coverage information based on your plan records, not medical or legal advice.
For questions about your care, please consult your doctor. To confirm benefits or file
an appeal, contact Member Services at 1-800-555-0100.


---

## Q3: Is physical therapy covered under my Silver plan?

**Classification:** both

<details>
<summary>Retrieved context (shared by all variants)</summary>


```
[Policy text, section: coverage]
The Gold PPO plan covers preventive care visits at no cost, emergency room visits subject to the
annual deductible, and prescription drugs under a tiered formulary. Surgical procedures require prior
authorization for non-emergency cases.

---

[Policy text, section: coverage]
This Summary of Benefits and Coverage (SBC) document describes the Gold PPO plan, a fictional
health plan created for training purposes. All figures below are synthetic and do not represent any real
insurance product.

---

[Policy text, section: coverage]
The claim is checked against the member's plan coverage rules, including deductible status and network tier. Claims are marked as Approved, Denied, or Pending further review.

---

[Policy text, section: coverage]
Silver HMO (P102): $300/month premium, $1500 annual deductible, 20% copay, network tier: Silver.

---

[Policy text, section: coverage]
Member Jane Test (Member ID M1001) submitted a claim for an X-ray procedure billed at $250 under the Gold PPO plan. The claim was marked Pending while deductible status was confirmed.
```

</details>


### Variant A — Strict/Formal

That information is not available in my records. Please contact Member Services.


### Variant B — Warm/Empathetic

The Silver HMO plan does not cover physical therapy. For information about what your Gold PPO plan covers, I'd be happy to help you further. What are you looking for coverage on with the Gold PPO?


### Variant C — Few-Shot

I apologize, but I don't have information about the coverage specifics of the Silver HMO plan in your records. Coverage details can vary significantly between plans and may not be fully detailed here. To confirm whether physical therapy is covered under your Silver HMO plan (P102), you should contact your insurance provider directly at 1-800-555-0100 or refer to the Summary of Benefits and Coverage (SBC) document for more specific details on what services are covered.


### Variant D — Chain-of-Thought

No specific information about policy details or coverage is provided in the context given. If you have further questions regarding your coverage or need assistance, please contact Member Services at 1-800-555-0100.


### Variant E — Hybrid

I don't have physical therapy benefits listed on the Silver HMO (P102) in your records. To confirm or learn more, please contact Member Services at 1-800-555-0100.

This is coverage information based on your plan records, not medical or legal advice.
For questions about your care, please consult your doctor. To confirm benefits or file
an appeal, contact Member Services at 1-800-555-0100.


---

## Q4: Is my X-ray procedure covered and what's my deductible under Silver HMO?

**Classification:** both

<details>
<summary>Retrieved context (shared by all variants)</summary>


```
[Policy text, section: coverage]
Member Jane Test (Member ID M1001) submitted a claim for an X-ray procedure billed at $250 under the Gold PPO plan. The claim was marked Pending while deductible status was confirmed.

---

[Policy text, section: coverage]
Silver HMO (P102): $300/month premium, $1500 annual deductible, 20% copay, network tier: Silver.

---

[Policy text, section: coverage]
The Gold PPO plan covers preventive care visits at no cost, emergency room visits subject to the
annual deductible, and prescription drugs under a tiered formulary. Surgical procedures require prior
authorization for non-emergency cases.

---

[Policy text, section: coverage]
The claim is checked against the member's plan coverage rules, including deductible status and network tier. Claims are marked as Approved, Denied, or Pending further review.

---

[Policy text, section: coverage]
Bronze HMO (P103): $150/month premium, $1000 annual deductible, 30% copay, network tier: Bronze.
```

</details>


### Variant A — Strict/Formal

That information is not available in my records. Please contact Member Services.


### Variant B — Warm/Empathetic

I understand you're looking for information about your current claim for an X-ray procedure and your deductibles with the different plans. Let’s break it down:

Under your Gold PPO plan, the X-ray procedure is not covered unless it’s a preventive care visit or an emergency room visit.

Regarding your Silver HMO, if the X-ray was not an emergency, you would need prior authorization from your employer or group administrator to proceed with the procedure. Once authorized, since it’s not specifically listed as covered, it's unclear whether it will be paid for under your network policy.

As far as deductibles are concerned:

- The Silver HMO has a $1500 annual deductible.
- For the Gold PPO, there’s no mention of deductibles in your provided context regarding this specific procedure.

Your best course of action is to contact Member Services at 1-800-555-0100 for the most accurate and detailed information about your X-ray claim and the Silver HMO's coverage rules. They can help verify if you have the authorization needed for the non-emergency case and confirm any additional details about deductibles.

Remember, the exact costs and insurance terms vary based on individual plan details, so it’s important to consult with your insurer directly for precise information.


### Variant C — Few-Shot

The Silver HMO plan has an annual deductible of $1,500. Under this plan, your claim for the X-ray procedure, billed at $250, would be covered as preventive care under your plan. Preventive care visits are typically covered at no cost according to the coverage information provided. You do not need to meet the annual deductible because this benefit is excluded from the deductible requirement.


### Variant D — Chain-of-Thought

Silver HMO (P102) covers preventive care, including X-rays, at no cost. The annual deductible is $1500.


### Variant E — Hybrid

I don't have that in your plan records. Member Services can help at 1-800-555-0100.

This is coverage information based on your plan records, not medical or legal advice.
For questions about your care, please consult your doctor. To confirm benefits or file
an appeal, contact Member Services at 1-800-555-0100.


---

## Q5: What is the claims submission process?

**Classification:** unstructured

<details>
<summary>Retrieved context (shared by all variants)</summary>


```
[Policy text, section: claims]
Members submit claims through the online portal or by mailing a completed claim form. Each claim must include the member ID, plan ID, date of service, and procedure code.

---

[Policy text, section: coverage]
This document outlines the fictional claims submission process used for training purposes. All names, member IDs, and procedures referenced are synthetic.

---

[Policy text, section: coverage]
Claims are reviewed for completeness within 3 business days. Incomplete claims are returned to the member with a request for additional information.

---

[Policy text, section: coverage]
The claim is checked against the member's plan coverage rules, including deductible status and network tier. Claims are marked as Approved, Denied, or Pending further review.

---

[Policy text, section: coverage]
Member Jane Test (Member ID M1001) submitted a claim for an X-ray procedure billed at $250 under the Gold PPO plan. The claim was marked Pending while deductible status was confirmed.
```

</details>


### Variant A — Strict/Formal

Members submit claims through the online portal or by mailing a completed claim form. Each claim must include the member ID, plan ID, date of service, and procedure code.


### Variant B — Warm/Empathetic

To submit a claim and get your expenses covered, follow these steps:

1. **Gather Requirements**: Ensure you have all necessary documents and a completed claim form.
2. **Submit Your Claim**:
   - You can submit your claim online through our portal or by mailing in a completed form.
   - Make sure to include your member ID (M1001), plan ID, date of service, and procedure code on the form.

3. **Check on Your Claim**: Once submitted, make sure you track its status. Claims are reviewed for completeness within 3 business days. If it's incomplete, you will be contacted to provide additional information.

I'm here to help if you have any other questions about your coverage or need further assistance!


### Variant C — Few-Shot

MemberJaneTest(M1001)submittedaclaimforanX-rayprocedurebilledat$250underthegoldPPOplan.
Theclaimsprocessincludesthesubmissionofcliamsthroughtheonlineportalormailingacompletedclaimform.
EachclaimmustincludethememberIDL,planID,dateofservice,andprocedurecode.

Claimsarereviewedforcompletenesswithindays. IncompleteclaimswillbereturnedmembersrequestrAdditionalinformation.

The claims are checked against the member's plan coverage rules, including deductible status and network tier. Claims are marked as Approved, Denied, or Pending further review.


### Variant D — Chain-of-Thought

Members submit claims through the online portal or by mailing a completed claim form. Each claim must include the member ID, plan ID, date of service, and procedure code. Claims are reviewed for completeness within 3 business days. Incomplete claims are returned to the member with a request for additional information. If complete, claims are checked against the member's plan coverage rules and marked as Approved, Denied, or Pending further review.


### Variant E — Hybrid

When submitting a claim, you should include:
- Your member ID
- Plan ID
- Date of service
- Procedure code

Claims are reviewed for completeness within 3 business days and may be marked as Approved, Denied, or Pending further review. You can submit claims through the online portal or by mailing a completed claim form.

This is coverage information based on your plan records, not medical or legal advice.
For questions about your care, please consult your doctor. To confirm benefits or file an appeal, contact Member Services at 1-800-555-0100.
