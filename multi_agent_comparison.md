# Day 22 — Multi-Agent Orchestration: Comparison to Day 21

Same 5 test questions from Day 21, run through a router + two-specialist
LangGraph workflow instead of Day 21's single ReAct agent. Router classifies
each question as "coverage" or "claims" (enrollment folds into "coverage"
since there's no dedicated enrollment tool — enrollment info lives in the
same RAG/vector store the Coverage Specialist already has access to, per
raw_text/faq.txt from Day 5). Model: llama3.1:8b via ChatOpenAI, same as
Day 21.

**API note:** same langgraph.prebuilt.create_react_agent deprecation warning
as Day 21 (moved to langchain.agents.create_agent in a future version) —
left as-is for the same reason: the code runs correctly, and switching
import paths without verifying the new API risks introducing an untested
change.

---

## Q1: What's the status of claim C1001?

**Day 21 (single agent):** Correct tool (get_claim_status_tool), correct
answer.

**Day 22 (multi-agent):** Router correctly classified as "claims" ->
Claims Specialist called get_claim_status_tool with the right claim ID ->
correct answer, essentially identical to Day 21.

**Comparison:** No meaningful difference. Simple, single-domain question —
routing overhead added a classification call but changed nothing about the
outcome.

---

## Q2: Is physical therapy covered under my Silver plan?

**Day 21 (single agent):** Correct tool (check_coverage_tool), correct
plan resolved, but final answer leaned toward "likely covered" language for
an "unknown" determination.

**Day 22 (multi-agent):** Router correctly classified as "coverage" ->
Coverage Specialist called check_coverage_tool with the same correct
arguments -> same "likely covered" looseness on the "unknown" result,
nearly word-for-word similar phrasing to Day 21.

**Comparison:** No improvement. This issue lives in how loosely both the
Day 21 AGENT_SYSTEM_PROMPT and Day 22's COVERAGE_SPECIALIST_PROMPT handle an
"unknown" determination — multi-agent routing doesn't touch this, since the
same underlying prompt looseness exists in both specialist prompts. A fix
here would mean tightening the specialist's system prompt to match
PRODUCTION_SYSTEM_PROMPT's stricter "never imply covered on an unknown
result" rule, not a routing change.

---

## Q3: What's the monthly premium for the Gold PPO plan?

**Day 21 (single agent):** Correct tool, correct plan, correct answer.

**Day 22 (multi-agent):** Router correctly classified as "coverage" ->
Coverage Specialist called get_plan_details_tool with the right plan_id ->
correct answer.

**Comparison:** No meaningful difference.


---

## Q4: How do I submit a claim?

**Day 21 (single agent):** WRONG in a dangerous way — invented a plan_id
(P102 / Silver HMO) with no basis in the question, then hallucinated a
placeholder website URL, phone number, and document checklist not present
in any tool output or retrieved context. This reproduced the exact failure
Day 13's check_argument_provenance() guard exists to catch.

**Day 22 (multi-agent):** Router classified as "claims" (arguably
defensible — the question contains the word "claim") -> Claims Specialist
has only get_claim_status_tool, which requires a claim ID -> no claim ID
was given, so the specialist called no tool and answered: "I cannot provide
information on how to submit a claim. Is there anything else I can help
you with?"

**Comparison:** Mixed result, not a clean win. The multi-agent version
avoided the dangerous failure mode (no invented plan_id, no hallucinated
contact details) — routing to a narrowly-tooled specialist meant there was
no plan_details tool available to misuse in the first place. But the
result is also unhelpful: the member gets no answer at all, even though
the actual claims-submission process is documented in
raw_text/claims_process.txt and is exactly the kind of general-process
question the RAG pipeline (rag_chatbot.py) answers correctly elsewhere in
this project. Neither specialist in this Day 22 graph has retrieval/vector
access wired in — Coverage Specialist's prompt claims scope over
"enrollment," but has no actual tool or retrieval call to draw on for a
general "how do I..." question, and Claims Specialist has even less: only
one tool, requiring an ID the question never provides.

**Root cause:** the safety improvement here is a side effect of narrower
tool scope, not a designed safeguard. Day 13's check_argument_provenance()
guard is still not wired into any agent path (Day 21 or Day 22) — the
actual fix (explicitly rejecting tool calls with unsupported arguments) is
still missing. What changed is that Day 22's Claims Specialist simply has
no tool to misuse for this question, so it fell back to a safe-but-useless
refusal instead of inventing data. A better fix would give both specialists
retrieval access for general-process questions, so "I don't know" isn't the
only safe option — an honest, correct answer already exists in the
knowledge base.

---

## Q5: What's the annual deductible on the Bronze HMO plan?

**Day 21 (single agent):** Correct tool, correct plan, correct answer.

**Day 22 (multi-agent):** Router correctly classified as "coverage" ->
Coverage Specialist called get_plan_details_tool with the right plan_id ->
correct answer.

**Comparison:** No meaningful difference.

---

## Summary

| # | Question | Day 21 result | Day 22 result | Multi-agent help? |
|---|---|---|---|---|
| 1 | Claim C1001 status | Correct | Correct | No difference |
| 2 | Silver PT coverage | Correct tool, loose phrasing on "unknown" | Same looseness | No improvement |
| 3 | Gold PPO premium | Correct | Correct | No difference |
| 4 | How to submit a claim | WRONG — invented plan_id + hallucinated details | Safe refusal, but unhelpful | Partial — avoided the dangerous failure, introduced a new unhelpful one |
| 5 | Bronze HMO deductible | Correct | Correct | No difference |

## When is multi-agent worth it?

Based on this 5-question comparison, multi-agent orchestration provided
**no measurable benefit on 4 of 5 questions** — questions with a clear,
single, correctly-named entity (a claim ID or a plan name) were answered
identically well by both the single Day 21 agent and the Day 22 router +
specialist graph. The routing step added latency (one extra LLM call per
question) without changing the outcome.

The one question where behavior differed (Q4) illustrates a real but
narrow benefit: **routing to a narrowly-scoped specialist can accidentally
prevent a specific class of hallucination** — a specialist with fewer tools
has fewer opportunities to misuse one. But this is an accidental side
effect of tool scoping, not a designed safeguard, and it traded a dangerous
failure (fabricated data) for a different failure (an unhelpful non-answer
to a question the system could have answered correctly via retrieval).

**Recommendation:** for this project's current tool set (three narrow,
well-defined lookups: coverage check, claim status, plan details),
multi-agent orchestration is not clearly worth its added complexity and
latency. The genuine problems found in this comparison — Day 13's
provenance guard not being ported into either agent path, the "unknown"
determination phrasing looseness, and neither specialist having retrieval
access for general questions — are all fixable at the prompt/tool-design
level, in either the single-agent or multi-agent architecture. Multi-agent
would likely earn its complexity if the domains were more genuinely
separate (e.g., a billing agent with entirely different tools and data
sources than a clinical-policy agent) rather than three variations on "look
up one record from one small SQLite database," which is what this project
actually has.
