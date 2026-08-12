# Session Handoff — Days 23 through 26

**Program:** ABTalks 60-Day AI Challenge
**Project:** Coverage Chatbot — RAG-governed healthcare coverage bot on Kubernetes
**Repo:** sharonkumar-us/my-first-app | Local: ~/projects/my-first-app
**Portal:** abtalks.in

---

## Where we are

Days 1-26 verified and closed on the portal. This handoff covers Day 23
(MCP server) through Day 26 (token governance + A/B testing) in detail;
see session_handoff_day15-19.md for earlier context.

---

## Day 23 — Model Context Protocol (MCP)

Built mcp_server.py exposing check_coverage_tool and get_claim_status_tool
(later get_plan_details_tool added Day 24) via mcp==2.0.0's
mcp.server.MCPServer (not the older FastMCP class most tutorials use in
this SDK version). Registered with Claude Desktop via
claude_desktop_config.json (backed up before editing, since it already had
substantial unrelated app settings).

**Major finding: relative-path fragility across the whole project.**
Claude Desktop launches the MCP server subprocess from a different working
directory than this project's terminal/uvicorn always used, which broke:
- retrieval_engine.py's Chroma client (`./chroma_data`)
- retrieval_engine.py's and tool_calling_chatbot.py's sqlite3 connections
  (`"coverage.db"`)
- rag_chatbot.py's `load_dotenv()` (no path, only found `.env` by luck of
  working directory)

Fixed all four by anchoring to `Path(__file__).resolve().parent`. Verified
by simulating Claude Desktop's launch conditions directly in the terminal
(running from `/` instead of the project root) rather than repeatedly
restarting the actual app. Documented in mcp_test_notes.md, including two
live tool tests through Claude Desktop's UI (both passed after the fix).

---

## Day 24 — Agentic Chatbot: Full Integration (MCP + memory + resilience)

Rewrote multi_agent.py (Day 22's router + specialists) to call tools
through a real MCP client (mcp.ClientSession over stdio) instead of direct
Python imports, wired in Day 20's memory (`_load_history` /
`_infer_plan_id`, imported from coverage-chatbot-api/main.py), and added
resilience: `asyncio.wait_for` with a 10s timeout, 1 retry, then a canned
fallback -- never a raw exception to the member.

**Major finding: LLM-judgment tool selection is unreliable.** The first
draft asked the LLM to decide via free text whether to call a tool.
Testing against the 5 standard questions showed llama3.1:8b answered
every question from its own general knowledge instead of calling any
tool -- entirely fabricated numbers (a $20 copay, a $405.92 premium, a
$3,000/$6,000 deductible split, none matching real data). Fixed by making
tool selection fully deterministic (regex/keyword matching, same pattern
as Day 19's `_try_build_cards` and Day 20's `_infer_plan_id`) -- the LLM
is now only used to phrase the final answer from real tool output, never
to decide whether to call a tool.

**Chaos test (chaos_test.md) took three attempts to get right:**
1. Renamed the underlying function -- broke at IMPORT time (wrong layer;
   a real bug should crash loudly, not be caught by resilience code).
2. Raised a RuntimeError inside the MCP tool -- the MCP SDK itself
   catches this and returns a normal-looking result describing the error,
   so this project's own retry/timeout logic never actually fired.
3. Injected a 15s sleep (exceeding the 10s timeout) -- this correctly
   exercised the real retry + fallback path: two timeout attempts, then
   the canned fallback message, no crash, no traceback. This is the
   genuine proof the resilience mechanism works.


---

## Day 25 — AI Governance, PHI Handling & Guardrails

Wrote GOVERNANCE.md grounded in a direct audit (not boilerplate): found
real synthetic PHI ("Member Jane Test, Member ID M1001") embedded
verbatim in knowledge_base.jsonl chunk10, and confirmed member_id was
being logged in plaintext on every /chat call. Built redact_pii.py
(member ID, claim ID, name, dollar-amount patterns; 4 unit tests) and
wired it into /chat and /chat/stream logging -- verified live via curl,
log line now shows `member=[MEMBER_ID_REDACTED]`.

Installed guardrails-ai (0.10.2; this downgraded huggingface-hub to 1.13.0
as a side effect -- verified sentence_transformers/retrieval_engine still
import cleanly afterward, no regression). Built two custom validators in
guardrails_config.py: PromptInjectionDetector (input) and
MedicalAdviceLeakage (output).

**Two genuine guardrail bugs found and fixed via adversarial testing
(adversarial_tests.md, 6 tests total -- portal asked for 5, a 6th
proof-of-concept was added after the first 5 passed for the wrong
reasons):**

1. **Output guardrail over-blocked legitimate answers.** The first
   version flagged ANY claim/member ID as a leak -- which would have
   blocked every correct claim-status answer this chatbot has ever given.
   Fixed by narrowing the check to member NAMES only (the actual
   re-identification risk), not bare IDs a member legitimately asked
   about.
2. **The narrowed fix then under-caught a real leak.** A live model
   answer said "I don't have Jane Test's full name..." -- leaking the
   real name in a phrasing the original MEMBER_NAME_PATTERN (which
   required the literal word "Member" before a name) didn't match. Fixed
   by adding a KNOWN_NAMES_PATTERN matching "Jane Test" in any phrasing,
   since this project's PHI surface is small and fully known via the
   audit.

GOVERNANCE.md's final section is explicit that this is a training
exercise, not a formal compliance review, and lists what a real review
would require (larger adversarial suite, legal sign-off on the redaction
approach, live monitoring, ingestion-time PHI review).

---

## Day 26 — Token Governance, Cost Management & Experiment Design

Built token_utils.py (`count_tokens`, reusing the same cl100k_base
encoding Day 20 already uses), wired into /chat via a new token_usage
SQLite table logging {session_id, timestamp, input_tokens, output_tokens,
estimated_cost}. Cost is explicitly labeled ILLUSTRATIVE -- this project's
LLM calls run through local Ollama and cost $0 in reality; the logged
"cost" uses OpenAI gpt-4o-mini's published rate purely to demonstrate the
mechanism.

**Bug found and fixed:** the first DB_PATH fix anchored to
`coverage-chatbot-api/`'s own directory (correct for a standalone script,
but main.py lives in a SUBDIRECTORY of the project root, where
coverage.db actually is) -- this silently created a second, near-empty
coverage.db inside coverage-chatbot-api/ rather than writing to the real
database. Caught immediately by checking the token_usage row's actual
location before assuming Step 2 worked; fixed to anchor one directory up
(`.parent.parent`).

Added a manual dict-based rate limiter (10 req/min/member, sliding
window) -- verified both in isolation (10 True, 2 False on 12 rapid
calls) and live over HTTP (10x 200, 1x 429 on 11 parallel curl requests).
Added an exact-match cache for general questions only, explicitly
excluding any message containing a claim ID or member ID pattern --
verified a repeat question dropped from 54s to 0.02s (cache hit), and
confirmed claim/member questions are correctly never cacheable.

**A/B experiment: Variant A ("Strict/Formal," from prompt_variants.md) vs
Variant E (current PRODUCTION_SYSTEM_PROMPT).** Found prompt_variants.md
was itself incomplete -- only Variant A's text exists, with an entirely
unscored table; Variants B-D were apparently never written, and Day 12's
"Variant E won 15/20" citation of this file doesn't actually have
supporting data in it. Ran a real, previously-uncompleted 15-question
comparison (ab_test.py, both variants answering from the SAME retrieved
context, isolating the comparison to prompt text only).

**Result: Variant E scored 8/15 "good" vs Variant A's 0/15** -- but this
gap is almost entirely a compliance-disclaimer artifact: Variant A's
prompt never instructs the model to include the disclaimer at all (11 of
its 15 misses are disclaimer-only failures on otherwise-correct answers).
Excluding disclaimer presence, Variant A is actually modestly stronger on
core accuracy/tone/conciseness.

**This run also surfaced four previously-undocumented issues in the
CURRENT PRODUCTION prompt (Variant E):**
1. A language-switching bug -- one answer (Q7, maternity coverage
   question) switched mid-response into Chinese.
2. Inconsistent disclaimer inclusion -- dropped entirely on 2 of 15
   answers (Q11, Q14), despite the prompt's rule 8 saying "no exceptions."
3. A PHI leak (Q15) -- "Jane Test" (the same chunk10 name from Day 25)
   leaked into an answer for an unrelated question. This ran through
   ab_test.py's direct LLM calls, NOT through /chat's guardrail pipeline
   -- meaning any code path outside coverage-chatbot-api/main.py's /chat
   endpoint currently has zero PHI-leak protection, a real gap.
4. Fabricated reasoning (Q8: justified X-ray coverage by miscategorizing
   it as "preventive care," which the context didn't actually support)
   and scope creep (Q9, Q12: unrequested extra detail).

ab_test_results.md's recommendation: keep Variant E in production (the
disclaimer requirement is real), but treat the four findings above as
open bugs, not just A/B noise.


---

## Known open items going forward

**High priority (real bugs, not yet fixed):**
1. **Variant E's language-switching bug (Day 26 Q7)** -- unexplained,
   only observed once, needs reproduction attempts before it can be
   diagnosed or fixed.
2. **Variant E's inconsistent disclaimer inclusion** -- dropped on 2 of
   15 real questions despite the prompt explicitly saying "no
   exceptions." The current prompt text is not sufficient on its own;
   needs either reinforcement or a code-level enforcement fallback
   (e.g. append the disclaimer programmatically if the model's own output
   doesn't include it, rather than relying on the prompt alone).
3. **No PHI-leak protection outside the /chat endpoint.** Day 25's output
   guardrail (guardrails_config.py) is only wired into
   coverage-chatbot-api/main.py's /chat. Day 26's ab_test.py (and
   potentially langchain_agent.py, multi_agent.py, or any other direct
   LLM-calling script) has zero PHI-leak protection. Confirmed
   exploitable: Day 26 Q15 leaked "Jane Test" with no guardrail catching
   it, since that code path doesn't go through /chat.
4. **Variant E's fabricated reasoning on Q8** -- claimed X-ray coverage
   was justified by "preventive care" language that doesn't actually
   support that conclusion. Not caught by any existing guardrail (this
   is a reasoning-quality issue, not a PHI/injection issue).

**Lower priority / already-documented, unresolved from earlier days:**
5. Day 10 SQL case-sensitivity and over-joining issues (Day 20's plan
   -label fix addressed the missing-plan-name issue specifically, but
   the broader SQL generation issues from Day 10 were not revisited).
6. Day 11 enrollment.txt chunk not surfacing in top-5 vector results.
7. Day 6 zero exclusions-tagged chunks in the knowledge base.
8. Day 21/22's finding that neither the single-agent nor multi-agent
   LangChain/LangGraph paths have Day 13's check_argument_provenance()
   guard wired in -- Day 24's multi_agent.py rewrite fixed this
   specifically for MCP-routed tool calls via deterministic tool
   selection, but langchain_agent.py (Day 21) still lacks the guard.

**Documentation gaps noted this session:**
9. prompt_variants.md (referenced since Day 12) only ever contained
   Variant A's text with an unscored table -- Variants B-D were never
   written up, despite rag_chatbot.py citing this file as the source for
   the "Variant E won 15/20" decision.
10. No session_handoff doc exists for Days 10-14 or Days 20-22 -- this
    handoff picks up from session_handoff_day15-19.md and covers Days
    23-26 specifically; the gap in between was not backfilled.

## Repository state

### Committed and pushed (Days 23-26)
- Day 23: mcp_server.py, mcp_test_notes.md, plus path-bug fixes to
  retrieval_engine.py, tool_calling_chatbot.py, rag_chatbot.py
- Day 24: multi_agent.py (rewritten), mcp_server.py (added
  get_plan_details_tool), chaos_test.md
- Day 25: GOVERNANCE.md, redact_pii.py, guardrails_config.py,
  adversarial_tests.md, adversarial_test.py, coverage-chatbot-api/main.py
  (logging redaction)
- Day 26: token_utils.py, coverage-chatbot-api/main.py (tokens, rate
  limit, cache), experiment_design.md, ab_test_results.md, ab_test.py

### Deliberately not committed
- ab_test_output.log, ab_test_raw_results.json (Day 26) -- intermediate
  artifacts; the scored write-up in ab_test_results.md is the actual
  deliverable
- coverage.db -- contains test-run data from local sessions; portal
  instructions for these days did not ask for it, consistent with the
  practice established since Day 20

### Standing environment notes (unchanged)
- macOS; always specify system Terminal vs. VS Code integrated terminal
- .venv (Python 3.14) for everything except Day 14-15 fine-tuning (ft_env,
  Python 3.12)
- Backend launch: `PYTHONPATH=. uvicorn main:app --reload --app-dir
  coverage-chatbot-api`
- Model split: qwen2.5-coder:7b for RAG/retrieval, llama3.1:8b for tool
  calling (only model that reliably emits structured tool_calls)

## Working principles held throughout (Days 23-26)

- Introspect library APIs directly (help(), dir()) before writing code
  against a new or updated dependency, rather than assuming tutorial-era
  APIs still apply -- caught real breaking changes in mcp, langgraph, and
  guardrails-ai this way.
- When a heredoc write is suspected to be truncated or duplicated, verify
  with `wc -l` and `grep -n "^#\|^##"` before trusting the file, rather
  than assuming success from terminal output alone.
- Simulate a failure's actual execution layer before writing a chaos test
  or debugging a bug -- Day 24's chaos test needed three attempts because
  the first two broke the wrong thing (import time, then a
  SDK-already-handled exception) rather than the layer the resilience
  code was actually meant to protect.
- Prefer deterministic pattern-matching over LLM judgment for
  safety-relevant decisions (tool selection, PHI redaction, cache
  eligibility) -- repeatedly proven more reliable than trusting a 7-8B
  local model's judgment calls in this project.
- Cross-check claims against actual data before writing documentation
  (GOVERNANCE.md's PHI findings, prompt_variants.md's incompleteness) --
  audit first, write second.
