# Day 24 — Chaos Test: Broken Tool + Fallback Verification

Goal: temporarily break one MCP tool, confirm the resilience wrapper
(10s timeout, 1 retry, canned fallback) prevents a crash or raw error from
reaching the member, then fix the break and confirm everything passes again.

Three attempts were made before landing on a test that actually exercised
the intended code path — each attempt surfaced a real finding, documented
below rather than skipped over.

---

## Attempt 1: renamed the underlying function (WRONG LAYER)

Renamed get_claim_status to get_claim_status_BROKEN in
tool_calling_chatbot.py, expecting the MCP tool call to fail at runtime.

**Result:** the whole script crashed immediately at import time, before any
question was even asked:

    NameError: name 'get_claim_status' is not defined

**Finding:** tool_calling_chatbot.py's module-level TOOL_DISPATCH dict
references get_claim_status by name at import time (not inside a function
body), so renaming it broke the import chain immediately. This is a
DIFFERENT failure class from what Day 24's resilience requirement targets —
an import-time NameError in this project's own code is a real bug that
should crash loudly during development, not be caught by a "graceful
fallback." Step 3's resilience wrapper is about runtime tool-call failures
(network errors, timeouts, a downstream service being unavailable) reaching
the member — not about hiding broken code. Reverted the rename and moved
the break to the correct layer: inside the MCP tool wrapper itself, which
runs at call time, not import time.

---

## Attempt 2: raised a RuntimeError inside the MCP tool (WRONG FAILURE MODE)

Changed get_claim_status_tool in mcp_server.py to raise
RuntimeError("Simulated outage...") instead of returning real data.

**Result:** the multi-agent workflow did NOT crash, and did produce a
reasonable-sounding answer ("The claims database is currently unavailable,
and I'm unable to retrieve the status of claim C1001.") — but log inspection
showed used_fallback was never True, and no retry attempt happened.

**Finding:** the MCP SDK itself catches exceptions raised inside a tool
function and wraps them into a normal-looking CallToolResult whose content
describes the error ("Error executing tool get_claim_status_tool: Simulated
outage..."). From this project's MCP client's perspective, the call
returned SUCCESSFULLY — no exception propagated up to
call_tool_resilient()'s try/except at all. The LLM was handed an
error-description string as if it were legitimate tool data and phrased a
plausible-sounding answer around it. The system degraded gracefully, but
NOT through the timeout/retry/fallback mechanism Step 3-4 actually asked
for — it worked by accident, because the MCP protocol has its own
error-wrapping layer that happened to produce something not completely
broken. This is worth flagging as a real limitation: THIS specific failure
mode (a tool function raising inside its own body) is already handled
gracefully by the MCP SDK, independent of anything this project built. Our
own retry/timeout code remained genuinely untested until Attempt 3.


---

## Attempt 3: injected a 15s hang (CORRECT — exercises timeout + retry)

Changed get_claim_status_tool in mcp_server.py to call time.sleep(15)
before returning — exceeding the 10s TIMEOUT_SECONDS this project's
call_tool_resilient() wraps every call in.

**Result: PASS.** Full sequence observed:

    [MCP call failed after 2 attempt(s)]:
    ...
    Action: get_claim_status_tool({'claim_id': 'C1001'})
    Observation: I'm having trouble accessing that right now, please contact member support. [FALLBACK USED]

- Two attempts were made (initial call + 1 retry), each hitting the 10s
  timeout, confirmed by a ~21 second gap between the first two HTTP log
  timestamps in the run.
- After both attempts timed out, call_tool_resilient() returned
  (FALLBACK_MESSAGE, True) exactly as designed.
- The specialist correctly treated used_fallback=True as a signal to return
  the canned message AS-IS, without asking the LLM to embellish or explain
  it further (per the explicit check in answer_claims_question /
  answer_coverage_question).
- No Python traceback, no crash, no raw exception text reached the final
  answer — the member-facing output was exactly: "I'm having trouble
  accessing that right now, please contact member support."
- Question 2 (next in the test sequence) proceeded completely normally
  immediately afterward — the failure was fully contained to the one
  broken tool call and did not cascade or leave the MCP session in a bad
  state.

This is the genuine, correctly-exercised proof that Step 3-4's
timeout + retry + fallback resilience works as designed.

---

## Fix confirmation (Step 6)

Reverted mcp_server.py's get_claim_status_tool to its original body
(removed the time.sleep(15) line). Re-ran the full 5-question test:

| # | Question | Result |
|---|---|---|
| 1 | Claim C1001 status | PASS — Pending, X-ray, $250, P101 |
| 2 | Silver HMO physical therapy coverage | PASS — correctly reported "cannot confirm" for an unknown determination |
| 3 | Gold PPO monthly premium | PASS — $500 |
| 4 | How do I submit a claim (no claim ID given) | PASS — honest refusal, no tool called, no hallucination |
| 5 | Bronze HMO annual deductible | PASS — $1,000 |

All 5 questions passed with real, correct data after the fix — confirming
the chaos test's break was fully isolated to its target and cleanly
reversible.

---

## Summary

The resilience wrapper (10s timeout via asyncio.wait_for, 1 retry, canned
fallback) works correctly when a tool call genuinely hangs or fails to
respond within the timeout window — the scenario most representative of a
real downstream outage. Two earlier chaos-test attempts, before landing on
the hang scenario, surfaced real findings worth keeping in mind:

1. Import-time errors in this project's own code (e.g. a typo'd function
   name referenced in a module-level dict) crash loudly and immediately,
   before this project's resilience code ever runs — which is correct
   behavior for a bug in the codebase, not something the fallback should
   or could paper over.
2. The MCP SDK has its own internal exception handling for tool functions
   that raise during execution — it converts a raised exception into a
   CallToolResult describing the error, rather than propagating the
   exception to the client. This means a tool function crashing internally
   is already handled somewhat gracefully by the protocol itself, separate
   from and prior to this project's own timeout/retry logic. Only failures
   that prevent a CallToolResult from coming back at all within the timeout
   window (hangs, dropped connections, a subprocess that stops responding)
   actually exercise this project's own resilience code — which is exactly
   what Attempt 3 tested.
