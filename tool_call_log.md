# Day 13 — Tool Call Log

Log of tool schema definition, model selection, and observed tool calls for the
coverage chatbot's function-calling layer.

---

## Model compatibility finding

Tool calling failed completely on the model used for Days 10–12, and the failure mode
was not obvious from the model's own metadata.

| Model | Params | Declares `tools`? | Actually works? | Notes |
|---|---|---|---|---|
| `qwen2.5-coder:7b` | 7B | **Yes** | **No** | Emitted tool calls as plain text in the message body instead of populating the `tool_calls` field |
| `qwen3.6:latest` | 36B MoE | Yes | Untested | Tool support is genuine, but the model is too large to run at usable speed on this machine — first probe did not complete |
| `llama3.1:8b` | 8B | Yes | **Yes** | Correct structured tool calls on every probe |

**Key lesson: a declared capability is not a working capability.** `ollama show
qwen2.5-coder:7b` lists `tools` under Capabilities, but the model produced output like:

```
CALL get_claim_status({"claim_id":"C1001"})
{"name":"check_coverage","arguments":{"plan_id":"P102","procedure":"physical therapy"}}
```

The model clearly understood *which* tool to call and *what arguments* to pass — it even
resolved "Silver plan" to `P102` correctly. It simply could not emit that decision through
the structured `tool_calls` field the SDK reads. Because `message.tool_calls` was empty,
the application saw no tool call at all.

This is a coding-tuned 7B model; instruction-following for structured output formats
appears to be the limitation, not comprehension of the task.

### Model split across the project (deliberate)

| File | Model | Reason |
|---|---|---|
| `retrieval_engine.py` | `qwen2.5-coder:7b` | Day 10 results measured against this model |
| `rag_chatbot.py` | `qwen2.5-coder:7b` | Day 11–12 results and prompt scoring measured against this model |
| `tool_calling_chatbot.py` | `llama3.1:8b` | Only model tested that emits structured tool calls reliably |

Changing the model in the first two files would invalidate the Day 10–12 test results and
the Day 12 prompt variant scoring, all of which were measured against `qwen2.5-coder:7b`.
The split is intentional and should stay until those days are re-run.

---

## System prompt adaptation

The Day 12 production prompt (Variant E) was reused as the base, per the mission steps.
Two of its rules directly conflict with tool calling:

- "Use ONLY the context provided"
- "When the context does not have the answer: I don't have that in your plan records."

On the first turn of a tool-calling exchange there is **no context by design** — fetching
it is the model's job. Left unqualified, these rules push the model toward refusing rather
than calling a tool.

A preamble was prepended to scope those rules so they apply only *after* tool results come
back, preserving the grounding guarantee without suppressing tool selection. The Day 12
prompt itself is imported unmodified from `rag_chatbot.py`, so there is still one source of
truth for it.

---

## Tool selection results — Step 2

Four tools attached via `tools=`. Model: `llama3.1:8b`.

| # | Question | Expected tool | Selected tool | Arguments | Result |
|---|---|---|---|---|---|
| 1 | What's the monthly premium for the Gold PPO plan? | `get_plan_details` | `get_plan_details` | `{'plan_id': 'P101'}` | ✅ |
| 2 | What's the status of claim C1001? | `get_claim_status` | `get_claim_status` | `{'claim_id': 'C1001'}` | ✅ |
| 3 | Is physical therapy covered under my Silver plan? | `check_coverage` | `check_coverage` | `{'plan_id': 'P102', 'procedure': 'physical therapy'}` | ✅ |
| 4 | How much would an MRI cost me on the Bronze HMO plan? | `estimate_out_of_pocket_cost` | `estimate_out_of_pocket_cost` | `{'procedure': 'MRI', 'plan_id': 'P103'}` | ✅ |
| 5 | How do I submit a claim? | *(no tool)* | `get_plan_details` | `{'plan_id': 'P101'}` | ❌ |

**Score: 4 correct selections out of 5. One false positive.**

### Observations

**Plan name resolution worked without being asked for explicitly.** The model mapped
"Gold PPO" → `P101`, "Silver plan" → `P102`, and "Bronze HMO" → `P103` in every case. This
came from the `enum` constraint plus the inline plan-name glosses in each `plan_id`
description — the model was never given a lookup table.

**Tool disambiguation held on the hardest pair.** `check_coverage` and
`estimate_out_of_pocket_cost` both take a procedure and a plan, and differ only in intent
(is it covered vs. what will it cost). Q3 and Q4 were routed correctly, which suggests the
mutual disclaimers in the descriptions ("Returns a coverage determination, not a cost
estimate" / "This is an estimate from plan terms, not a quoted price") are doing real work.

**The negative case failed, and it is the most important result of the step.** Q5 asks a
general process question — no plan, no claim, nothing to look up. The model called
`get_plan_details({'plan_id': 'P101'})`.

Two distinct failures are stacked in that one call:

*It reached for a tool when none applied.* The tool-calling preamble explicitly names this
exact situation as a no-tool case, using the phrase **"how do I submit a claim?"** verbatim
as its example. The model called a tool anyway. A negative instruction — even one quoting
the test question word for word — did not overcome the model's bias toward acting. Tool
availability appears to create pressure to use tools.

*It invented a plan.* The question mentions no plan whatsoever. `P101` was chosen from
nowhere. The `enum` did its job in the narrow sense — the value is valid, not malformed —
but this exposes its actual limit: **an enum constrains which value gets picked, not
whether picking one was warranted.** Schema-level validation catches invalid arguments; it
cannot catch an unwarranted call. That has to be handled at the prompt or application
layer.

Consequence for the pipeline: had the execution loop been live, this would have fetched
Gold PPO's premium and deductible and handed them to the model as context for a question
about claim submission. The Day 12 grounding prompt would then have been working from
confidently-retrieved, entirely irrelevant data — a worse starting position than empty
context, because it looks legitimate.

Candidate fixes to test once the execution loop exists:

1. State the no-tool condition as a positive rule rather than an exception — e.g. "Process
   and procedure questions are answered from your own knowledge; tools are only for
   member-specific or plan-specific lookups."
2. Add a required-context check to the tool descriptions themselves: `get_plan_details`
   could specify that it must not be called unless the member has named a plan.
3. Validate at the application layer — reject tool calls whose arguments do not appear,
   directly or by clear synonym, in the member's question.

Option 3 is the only one that does not depend on model compliance, and is the most likely
to hold up.

---

## Failure modes observed before the model swap

Recorded because they are prompt-design lessons independent of the tool-calling plumbing,
and they may resurface on other models.

**Clarifying-question loop.** On `qwen2.5-coder:7b`, Q1 responded: "can you clarify which
plan you're inquiring about? Is it Gold PPO (P101), Silver HMO (P102), or Bronze HMO
(P103)?" — while the question already named Gold PPO, and the answer was listed in the
model's own clarifying question. This is the Day 12 refusal instinct surviving the
tool-calling preamble.

**Deferring instead of acting.** Q4 responded "I'll need to know your specific plan
details. Please provide the plan ID (P103)..." — again supplying the answer inside the
request for it. Both cases show a model trained toward caution treating tool invocation as
something requiring permission rather than as the expected action.

Neither behaviour appeared on `llama3.1:8b`.

---

*Sections below to be completed as later steps are built: tool execution loop, Pydantic
response validation, and full 5+1 test results.*

---

## Step 3 — Execution loop results

The loop works end to end: on a tool call it runs the matching Python function against
`coverage.db` (or the vector store, for `check_coverage`), feeds the JSON result back as a
`tool`-role message, and returns the model's final natural-language answer from a second
turn.

The dominant finding is **run-to-run nondeterminism**. The same five questions were run
twice against identical code, and three answers changed between runs.

| Q | Run 1 | Run 2 | Tool result (both runs) |
|---|---|---|---|
| Q1 — Gold PPO premium | Disclaimer only, premium dropped ❌ | Correct: "$500 monthly premium" ✅ | `monthly_premium: 500` (correct both times) |
| Q2 — claim C1001 status | Correct + minor overreach | Correct + minor overreach | `status: Pending` (correct) |
| Q3 — physical therapy / Silver | "unknown... not clearly addressed" ✅ | "The Silver HMO covers physical therapy" ❌ | `determination: unknown` (correct both times) |
| Q4 — MRI cost / Bronze | Honest, gave deductible + copay ✅ | Honest, gave deductible + copay ✅ | deductible $1000, copay 30% (correct) |
| Q5 — submit a claim | `plan_id: 'none named'` → tool error → recovered | `plan_id: 'P101'` invented → answered anyway | n/a (no tool should have been called) |

**The tool layer is deterministic; the model's second turn is not.** In every row above the
tool returned the same correct result both times. Every discrepancy was introduced when the
model composed its final answer from that result. This locates the reliability problem
precisely: not in retrieval, not in tool execution, but in the turn-2 generation step.

### Q3 is the most serious finding

Run 1 relayed the tool's `unknown` determination honestly. Run 2 overwrote it with a
confident **"The Silver HMO covers physical therapy"** — a fabricated coverage
confirmation, the exact Day 12 Variant B failure the `check_coverage` tool was designed to
prevent.

The tool did its job: it returned `determination: unknown` with an explicit note that
unknown does not mean covered. The model ignored the note and asserted coverage anyway.

**Lesson: a tool that returns an honest result does not guarantee an honest answer.** The
grounding guarantee holds only if the model faithfully relays the tool output, and on a
short factual turn it does not reliably do so. The fix cannot live in the tool alone — it
needs either a stricter turn-2 instruction ("state the tool's determination verbatim; never
upgrade 'unknown' to 'covered'") or a post-generation check that the answer does not assert
more than the tool returned.

### Q1 — disclaimer-only failure (intermittent)

On the first run, Q1's answer was the closing disclaimer alone — the $500 premium the tool
returned was dropped entirely. On rerun it was correct. Direct test confirmed the tool
returns the premium reliably (`get_plan_details('P101')` →
`{'monthly_premium': 500, ...}`), so this is the same class of turn-2 flake as Q3: the
model satisfied the "append the disclaimer verbatim" rule while omitting the answer body.
The strong disclaimer requirement appears able to stand in for the whole response when the
model is being lazy on a short turn.

### Q2 — minor overreach

Both runs correct on the core fact (status Pending) but added unsupported gloss — "the plan
is covering some costs" / "has not yet processed or paid." The tool returned only status,
procedure, and amount. Low-severity, but the same pattern: the model adds detail the tool
did not provide.

### Q5 — false positive persists, but shifted

The negative case still fails, differently each run. Run 1: the model recognized no plan was
named, passed `plan_id: 'none named'` (not a valid enum value), the tool returned an error,
and the model recovered by answering from general knowledge. Run 2: it reverted to inventing
`P101`, ran the tool, ignored the irrelevant result, and answered the process question
anyway. Both produced acceptable final answers, but by luck of recovery rather than by
correctly declining the tool. The application-layer guard proposed in Step 2 (reject tool
calls whose arguments do not appear in the question) remains the right fix and is not yet
implemented.

### Deterministic tool behaviors confirmed

- **Parameterized queries.** `get_claim_status` and `get_plan_details` use `WHERE col = ?`
  with the value bound separately, never string-formatted. This structurally removes the
  Day 10 SQL case-sensitivity and injection surface — a claim id either matches or returns
  a clean "no claim found," with no way to break the query.
- **No fabricated cost figures.** `estimate_out_of_pocket_cost` returns the deductible and
  copay it can compute plus an explicit "exact price not in records" note, rather than
  inventing a dollar amount. Q4 relayed this faithfully in both runs.
- **Coverage cannot fabricate a denial.** `check_coverage` returns `likely_covered` or
  `unknown`, never `not_covered`, because the Day 6 knowledge base has no exclusions data.
  The tool holds this line; the risk is the model overriding it (see Q3).

---

## Step 4 — Pydantic validation

Every tool result is now validated against a Pydantic model before it is serialized back
to the model. Five models: `PlanDetails`, `ClaimStatus`, `CostEstimate`, `CoverageResult`,
and a shared `ErrorResponse` for unknown plan/claim ids. Validation runs inside the
execution loop between calling the tool and appending its result to the conversation.

All four tool responses validated cleanly this run — visible in the `validated ->` lines,
each emitting well-formed JSON matching its model's contract.

### What validation does and does not cover

**Covers — tool output shape.** A tool that returns the wrong type, a missing field, or a
malformed dict is caught here and replaced with a structured `ErrorResponse` instructing
the model not to answer from it. A broken tool can no longer feed garbage into a coverage
answer. Error results (unknown plan/claim) now arrive in a uniform validated shape rather
than as raw exception strings.

**Does NOT cover — answer faithfulness on turn 2.** Pydantic validates what the tool
*returns*, not what the model *does* with it afterward. The Day 13 Q3 failure — the model
upgrading an `unknown` determination to a confident "covered" — happens after validation,
during generation. Pydantic is structurally incapable of catching it. This was expected and
is called out in the code comments; validation is the wrong layer for that class of bug.

### Q3 held this run — but the nudge is not a fix

A line was added to the preamble: "if a coverage determination is 'unknown', say it is
unknown — do NOT upgrade it to covered." This run Q3 relayed the `unknown` honestly ("I
don't have information ... about physical therapy coverage").

This must not be read as solved. The previous run produced the fabricated "covers physical
therapy" from the *identical* tool output (`determination: unknown`). Same input, different
answer. The nudge shifts the probability; it does not remove the failure mode. The only
reliable fix is a post-generation check that the answer does not assert coverage the tool
marked unknown — a guard, not a prompt line. Logged as open.

### Persistent minor overreach

The model continues to add small details the tool did not return: Q2 stated the member
"will be notified by mail" (no notification method is in the tool result). Harmless here,
same root pattern as the Q3 risk — the model embellishing validated data on turn 2.

### Q5 false positive — why validation did not catch it

Q5 ("how do I submit a claim?") again triggered an unwarranted `get_plan_details('P101')`.
Pydantic did not flag it because `P101` is a *valid* plan — the returned data satisfies
`PlanDetails` perfectly. The problem is not the shape of the result but the fact that the
call was unwarranted: no plan appears in the question. This confirms the Step 2 analysis —
**an enum constrains values, Pydantic constrains shapes; neither constrains whether a call
was justified.** The argument-provenance check (reject tool calls whose arguments do not
appear in the member's question) remains the correct fix and is still the top open item.
The final answer was acceptable only because the model ignored the irrelevant plan data.

### Pydantic v2 note

Uses `model(**result).model_dump_json()` (v2). The v1 equivalents (`parse_obj`, `.json()`)
would fail on the installed Pydantic 2.13.4.

---

## Step 5 — 5+1 Tool Selection Test

**Result: 6/6 correct tool selection.**

| # | Question | Expected | Selected | Pass |
|---|---|---|---|---|
| 1 | What's the monthly premium for the Gold PPO plan? | `get_plan_details` | `get_plan_details` | ✅ |
| 2 | What's the status of claim C1001? | `get_claim_status` | `get_claim_status` | ✅ |
| 3 | Is physical therapy covered under my Silver plan? | `check_coverage` | `check_coverage` | ✅ |
| 4 | How much would an MRI cost me on the Bronze HMO plan? | `estimate_out_of_pocket_cost` | `estimate_out_of_pocket_cost` | ✅ |
| 5 | What's the annual deductible on the Bronze HMO plan? | `get_plan_details` | `get_plan_details` | ✅ |
| 6 | How do I submit a claim? | `none` | `none (correct)` | ✅ |

**How Q6 passed:** the provenance guard added in Step 5 rejects any tool call whose
identifier arguments (`plan_id`, `claim_id`) do not trace back to the member's question —
either the id itself or a plan-name hint ("Silver plan" → P102). On "how do I submit a
claim?" no plan is named, so a `get_plan_details` call with an invented `plan_id` is
rejected before the tool runs, and the model answers the process question from general
knowledge. This is the fix proposed as far back as Step 2. It is the only one of the three
candidate fixes that does not depend on model compliance — the enum constrains *values*,
Pydantic constrains *shape*, and the guard constrains *warrant*, closing the gap the first
two could not.

**Scope note on the 5th tool.** The project defines four tools, so five *distinct* tools is
not possible. Case 5 exercises `get_plan_details` from a different angle (deductible rather
than premium) to cover a fifth distinct question path. All four tools are exercised across
the six cases.

**Still open (not a tool-selection failure, so does not affect the 6/6):** the turn-2
faithfulness problem — the model occasionally overstating a validated tool result when
composing its final answer (Day 13 Q3 "unknown → covered", Q2 invented notification method).
Tool *selection* is now reliable; answer *faithfulness* to the selected tool's result is
not, and remains the top open item for a later day.

---

## Step 5 — 5+1 Tool Selection Test

**Result: 6/6 correct tool selection.**

| # | Question | Expected | Selected | Pass |
|---|---|---|---|---|
| 1 | What's the monthly premium for the Gold PPO plan? | `get_plan_details` | `get_plan_details` | ✅ |
| 2 | What's the status of claim C1001? | `get_claim_status` | `get_claim_status` | ✅ |
| 3 | Is physical therapy covered under my Silver plan? | `check_coverage` | `check_coverage` | ✅ |
| 4 | How much would an MRI cost me on the Bronze HMO plan? | `estimate_out_of_pocket_cost` | `estimate_out_of_pocket_cost` | ✅ |
| 5 | What's the annual deductible on the Bronze HMO plan? | `get_plan_details` | `get_plan_details` | ✅ |
| 6 | How do I submit a claim? | `none` | `none (correct)` | ✅ |

---

## Tool Call Audit — 2026-07-30 16:21:52

Per-call trail for the 5+1 harness run. Each entry captures the model's tool
choice, the arguments passed, whether the provenance guard accepted the call,
and the validated tool result the model saw on turn 2.


### Case 1: What's the monthly premium for the Gold PPO plan?

**Call 1 — executed**
- tool: `get_plan_details`
- arguments: `{"plan_id": "P101"}`
- validated result: `{"plan_id":"P101","plan_name":"Gold PPO","monthly_premium":500,"annual_deductible":2000,"copay_pct":10,"network_tier":"Gold"}`


### Case 2: What's the status of claim C1001?

**Call 1 — executed**
- tool: `get_claim_status`
- arguments: `{"claim_id": "C1001"}`
- validated result: `{"claim_id":"C1001","status":"Pending","procedure":"X-ray","claim_amount":250,"plan_id":"P101"}`


### Case 3: Is physical therapy covered under my Silver plan?

**Call 1 — executed**
- tool: `check_coverage`
- arguments: `{"plan_id": "P102", "procedure": "physical therapy"}`
- validated result: `{"plan_id":"P102","plan_name":"Silver HMO","procedure":"physical therapy","determination":"unknown","policy_snippets":["Silver HMO (P102): $300/month premium, $1500 annual deductible, 20% copay, network tier: Silver.","Bronze HMO (P103): $150/month premium, $1000 annual deductible, 30% copay, network tier: Bronze.","This Summary of Benefits and Coverage (SBC) document describes the Gold PPO plan, a fictional\nhealth plan created for training purposes. All figures below are synthetic and do not represent any real\ninsurance product."],"note":"Determination is based only on retrieved policy text. 'unknown' means the policy text does not clearly address this procedure — it does NOT mean the service is excluded. The knowledge base has no exclusions data, so coverage denials cannot be confirmed here; direct the member to Member Services."}`


### Case 4: How much would an MRI cost me on the Bronze HMO plan?

**Call 1 — executed**
- tool: `estimate_out_of_pocket_cost`
- arguments: `{"procedure": "MRI", "plan_id": "P103"}`
- validated result: `{"procedure":"MRI","plan_id":"P103","plan_name":"Bronze HMO","annual_deductible":1000,"copay_pct":30,"estimate_note":"Assuming the $1000 annual deductible has not yet been met, the member pays the full negotiated cost of 'MRI' until the deductible is reached, then 30% coinsurance after that. An exact figure requires the negotiated procedure price, which is not in plan records."}`


### Case 5: What's the annual deductible on the Bronze HMO plan?

**Call 1 — executed**
- tool: `get_plan_details`
- arguments: `{"plan_id": "P103"}`
- validated result: `{"plan_id":"P103","plan_name":"Bronze HMO","monthly_premium":150,"annual_deductible":1000,"copay_pct":30,"network_tier":"Bronze"}`


### Case 6: How do I submit a claim?

**Call 1 — REJECTED (provenance guard)**
- tool: `get_plan_details`
- arguments: `{"plan_id": "P101"}`
- validated result: `{"error":"Rejected get_plan_details: plan_id 'P101' was not named or implied in the question. The model appears to have invented it."}`

