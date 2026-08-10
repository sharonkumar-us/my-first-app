# Day 21 — LangChain ReAct Agent Traces

5 test questions run through a langgraph.prebuilt.create_react_agent wrapping
the Day 13 tools (check_coverage, get_claim_status, get_plan_details) as
LangChain @tool-decorated functions. Model: llama3.1:8b via ChatOpenAI
pointed at the local Ollama server — same model Day 13 uses for tool calling.

**API note:** this LangChain version (1.3.14 / langgraph 1.2.10) no longer has
langchain.agents.create_react_agent / AgentExecutor — the ReAct agent now
lives in langgraph.prebuilt.create_react_agent, and it has no verbose=True
console log. Instead it returns the full message history, which is reformatted
into an equivalent Thought -> Action -> Observation -> Final Answer trace below.

**Known deprecation (not fixed this session):** running the script prints a
LangGraphDeprecatedSinceV10 warning that create_react_agent has moved to
langchain.agents.create_agent. The code runs correctly despite this — left
as-is to avoid introducing an unverified API surface change; worth revisiting
if a future LangChain upgrade removes the deprecated path entirely.

---

## Q1: What's the status of claim C1001?

**Tool(s) called:** get_claim_status_tool

**Human coverage-support rep would:** Look up the claim by ID — a rep would
pull up the claim record directly.

**Reasoning trace:**

    Action: get_claim_status_tool({'claim_id': 'C1001'})
    Observation: claim_id C1001, status Pending, procedure X-ray, claim_amount 250, plan_id P101
    Final Answer: The status of claim C1001 is pending. The claim is for an X-ray procedure and has a total amount of $250 under plan P101.

**Match:** Correct — correct tool, correctly-sourced claim ID (C1001 was
explicitly named in the question).

---

## Q2: Is physical therapy covered under my Silver plan?

**Tool(s) called:** check_coverage_tool

**Human coverage-support rep would:** Check the Silver plan's coverage rules
for physical therapy — a rep would consult the plan's benefit summary.

**Reasoning trace:**

    Action: check_coverage_tool({'plan_id': 'P102', 'procedure': 'physical therapy'})
    Observation: plan_id P102, plan_name Silver HMO, determination unknown, policy_snippets [...]
    Final Answer: Based on the tool output, physical therapy is likely covered under your Silver plan since there's no note indicating that it's excluded and the policy text doesn't clearly address this procedure (indicated by 'unknown'). However, coverage can only be confirmed or denied with a specific determination from Member Services.

**Match:** Correct tool, correctly-sourced plan (Silver named maps to P102).
Minor concern: the final answer leans toward "likely covered" language for
an unknown determination — the project's PRODUCTION_SYSTEM_PROMPT
(rag_chatbot.py) explicitly forbids that framing, but this LangChain agent's
own AGENT_SYSTEM_PROMPT is much shorter and doesn't carry that same
discipline. The tool itself correctly refused to fabricate a denial or
approval — the looseness is in how the agent phrased the final answer.


---

## Q3: What's the monthly premium for the Gold PPO plan?

**Tool(s) called:** get_plan_details_tool

**Human coverage-support rep would:** Look up the Gold PPO plan's standard
terms — a rep would pull plan details, not a claim or a coverage
determination.

**Reasoning trace:**

    Action: get_plan_details_tool({'plan_id': 'P101'})
    Observation: plan_id P101, plan_name Gold PPO, monthly_premium 500, annual_deductible 2000, copay_pct 10, network_tier Gold
    Final Answer: The monthly premium for the Gold PPO plan is $500 per month.

**Match:** Correct — correct tool, correctly-sourced plan (Gold PPO named
maps to P101), answer factually correct and appropriately concise.

---

## Q4: How do I submit a claim?

**Tool(s) called:** get_plan_details_tool

**Human coverage-support rep would:** Answer from general process knowledge —
a rep would explain the submission steps without looking up any specific
member's plan or claim data, since none was named.

**Reasoning trace:**

    Action: get_plan_details_tool({'plan_id': 'P102'})
    Observation: plan_id P102, plan_name Silver HMO, monthly_premium 300, annual_deductible 1500, copay_pct 20, network_tier Silver
    Final Answer: You can submit a claim through our online portal or by mailing it to the address on your member ID card. To begin the submission process, please create an account on our website ([website URL]) or call us at (phone number) for assistance. Also, make sure to have the following documents ready: a copy of your itemized medical bill, your insurance card, any supporting documentation (e.g., doctor's notes, receipts).

**Match:** WRONG. Two distinct failures on this question:

1. Invented a plan_id. No plan was named anywhere in "How do I submit a
   claim?" — the agent called get_plan_details_tool(plan_id='P102') (Silver
   HMO) with no basis for that choice. This is the exact failure mode Day
   13's check_argument_provenance() guard exists to catch (see
   tool_calling_chatbot.py) — but that guard lives in Day 13's own
   execution loop (answer_question()), which this LangChain agent bypasses
   entirely by calling the raw tool functions (get_plan_details) directly
   rather than going through Day 13's provenance-checked wrapper. Real,
   reproducible gap: this LangChain agent has no equivalent safety guard.
2. Fabricated specifics not in any context. The final answer includes a
   placeholder website URL, a placeholder phone number, and a document
   checklist — none of which came from the tool's output (which was just
   Silver HMO's cost-sharing terms) or from any retrieved policy text. This
   is a hallucination layered on top of the wrong tool call.

Root cause: AGENT_SYSTEM_PROMPT (this file) is much shorter and looser than
PRODUCTION_SYSTEM_PROMPT (rag_chatbot.py) or Day 13's TOOL_CALLING_PREAMBLE
plus provenance guard combination — it tells the agent to use tools
"whenever a question needs plan terms" but doesn't define what counts as a
plan being specified, and has no fabrication guardrail at all.

---

## Q5: What's the annual deductible on the Bronze HMO plan?

**Tool(s) called:** get_plan_details_tool

**Human coverage-support rep would:** Look up the Bronze HMO plan's standard
terms — same as the premium question, just a different field.

**Reasoning trace:**

    Action: get_plan_details_tool({'plan_id': 'P103'})
    Observation: plan_id P103, plan_name Bronze HMO, annual_deductible 1000, monthly_premium 150, copay_pct 30, network_tier Bronze
    Final Answer: The annual deductible for the Bronze HMO plan is $1,000.

**Match:** Correct — correct tool, correctly-sourced plan (Bronze HMO named
maps to P103), answer factually correct.

---

## Step 5 — Tool-selection quality comparison

| # | Question | Tool(s) called | Matches human rep expectation? |
|---|---|---|---|
| 1 | What's the status of claim C1001? | get_claim_status_tool | Yes |
| 2 | Is physical therapy covered under my Silver plan? | check_coverage_tool | Yes (tool correct; answer phrasing slightly loose on an "unknown" result) |
| 3 | What's the monthly premium for the Gold PPO plan? | get_plan_details_tool | Yes |
| 4 | How do I submit a claim? | get_plan_details_tool | No — invented plan_id, should have called no tool at all |
| 5 | What's the annual deductible on the Bronze HMO plan? | get_plan_details_tool | Yes |

Result: 4/5 correct tool selection, 1 clear miss.

## Findings summary

- 4 of 5 questions: correct tool selected, arguments correctly traced back
  to what the member actually said.
- 1 of 5 questions (Q4): wrong tool call driven by an invented plan_id, plus
  a hallucinated answer with fabricated placeholder contact details. This
  reproduces the exact failure Day 13's check_argument_provenance() guard
  was built to prevent — but that guard is not wired into this LangChain
  agent, since it wraps the raw Day 13 tool functions rather than Day 13's
  provenance-checked execution loop.
- Q2 finding: the agent's own system prompt is materially looser than the
  project's PRODUCTION_SYSTEM_PROMPT around how to phrase an "unknown"
  coverage determination — worth tightening if this agent path is used for
  anything beyond this exercise.

Not fixed in this session (documenting rather than resolving, to avoid scope
drift beyond Day 21's stated objectives): porting check_argument_provenance()
into this LangChain agent, and aligning AGENT_SYSTEM_PROMPT with
PRODUCTION_SYSTEM_PROMPT's stricter rules. Both would be natural follow-ups
if this agent becomes more than a Day 21 exercise.
