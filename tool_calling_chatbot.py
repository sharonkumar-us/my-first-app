"""
Day 13 — Tool Calling & Structured Outputs.

Step 1: JSON schemas for the four coverage tools.
Step 2: Pass those schemas to the model via tools=, with the Day 12 system prompt.
Step 3: Execute the chosen tool, feed the result back, get the final answer.
Step 4: Validate every tool response with Pydantic BEFORE returning it to the model.

Model note: tool calling runs on llama3.1:8b. qwen2.5-coder:7b declares tool
support but emits calls as plain text; see tool_call_log.md.
"""

import json
import os
import sqlite3
from datetime import datetime

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, ValidationError

from rag_chatbot import PRODUCTION_SYSTEM_PROMPT
from retrieval_engine import vector_lookup

load_dotenv()

client = OpenAI(
    base_url=os.environ["OLLAMA_BASE_URL"],
    api_key=os.environ["OLLAMA_API_KEY"],
)

# llama3.1:8b emits structured tool_calls reliably; the coder model does not.
GENERATION_MODEL = "llama3.1:8b"

DB_PATH = "coverage.db"
PLAN_IDS = ["P101", "P102", "P103"]

# ---------------------------------------------------------------------------
# TOOL SCHEMAS
# ---------------------------------------------------------------------------

CHECK_COVERAGE_SCHEMA = {
    "type": "function",
    "function": {
        "name": "check_coverage",
        "description": (
            "Check whether a specific medical procedure or service is covered under a "
            "given health plan. Use this when the member asks whether something is "
            "covered, included, or paid for — for example 'is physical therapy covered "
            "on my Silver plan?'. Returns a coverage determination, not a cost estimate."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {
                    "type": "string",
                    "enum": PLAN_IDS,
                    "description": (
                        "The plan identifier: P101 (Gold PPO), P102 (Silver HMO), "
                        "or P103 (Bronze HMO)."
                    ),
                },
                "procedure": {
                    "type": "string",
                    "description": (
                        "The medical procedure or service to check, in plain language — "
                        "for example 'physical therapy', 'X-ray', 'maternity care'."
                    ),
                },
            },
            "required": ["plan_id", "procedure"],
        },
    },
}

GET_CLAIM_STATUS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_claim_status",
        "description": (
            "Look up the current processing status of a submitted claim by its claim ID. "
            "Use this when the member asks about a specific claim — its status, whether "
            "it was approved or denied, or what happened to it. Requires a claim ID; do "
            "not call this tool if the member has not given one."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "claim_id": {
                    "type": "string",
                    "description": (
                        "The claim identifier as the member stated it, for example "
                        "'C1001'. Pass it through exactly as given — do not correct, "
                        "reformat, or guess at a claim ID."
                    ),
                }
            },
            "required": ["claim_id"],
        },
    },
}

GET_PLAN_DETAILS_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_plan_details",
        "description": (
            "Retrieve the standard terms of a health plan: monthly premium, annual "
            "deductible, copay percentage, and network tier. Use this for questions "
            "about what a plan costs or how its cost-sharing works. Does not say "
            "whether any particular procedure is covered — use check_coverage for that."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "plan_id": {
                    "type": "string",
                    "enum": PLAN_IDS,
                    "description": (
                        "The plan identifier: P101 (Gold PPO), P102 (Silver HMO), "
                        "or P103 (Bronze HMO)."
                    ),
                }
            },
            "required": ["plan_id"],
        },
    },
}

ESTIMATE_OUT_OF_POCKET_COST_SCHEMA = {
    "type": "function",
    "function": {
        "name": "estimate_out_of_pocket_cost",
        "description": (
            "Estimate what a member would pay out of pocket for a procedure under a "
            "given plan, based on that plan's deductible and copay. Use this when the "
            "member asks how much something will cost them, what they will owe, or what "
            "their share is. This is an estimate from plan terms, not a quoted price."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "procedure": {
                    "type": "string",
                    "description": (
                        "The medical procedure or service being priced, in plain "
                        "language — for example 'X-ray', 'MRI', 'specialist visit'."
                    ),
                },
                "plan_id": {
                    "type": "string",
                    "enum": PLAN_IDS,
                    "description": (
                        "The plan identifier: P101 (Gold PPO), P102 (Silver HMO), "
                        "or P103 (Bronze HMO)."
                    ),
                },
            },
            "required": ["procedure", "plan_id"],
        },
    },
}

TOOLS = [
    CHECK_COVERAGE_SCHEMA,
    GET_CLAIM_STATUS_SCHEMA,
    GET_PLAN_DETAILS_SCHEMA,
    ESTIMATE_OUT_OF_POCKET_COST_SCHEMA,
]

# ===========================================================================
# PYDANTIC RESPONSE MODELS
#
# One model per tool, describing the exact shape that tool is allowed to hand
# back to the LLM. Every tool result is validated against its model before it is
# serialized into the conversation. A tool that returns a malformed dict (wrong
# type, missing field, out-of-range value) is caught HERE rather than silently
# feeding garbage to the model.
#
# Note on scope: Pydantic validates the tool's OUTPUT SHAPE. It cannot catch the
# model later overstating that output on turn 2 (the Day 13 Q3 "unknown -> covered"
# problem) — that happens after validation, in generation. Handled separately by
# the ErrorResponse fallback + prompt discipline, not here.
# ===========================================================================

class PlanDetails(BaseModel):
    plan_id: str
    plan_name: str
    monthly_premium: int
    annual_deductible: int
    copay_pct: int
    network_tier: str


class ClaimStatus(BaseModel):
    claim_id: str
    status: str
    procedure: str
    claim_amount: int
    plan_id: str


class CostEstimate(BaseModel):
    procedure: str
    plan_id: str
    plan_name: str
    annual_deductible: int
    copay_pct: int
    estimate_note: str


class CoverageResult(BaseModel):
    plan_id: str
    plan_name: str
    procedure: str
    determination: str  # "likely_covered" or "unknown" — never a fabricated denial
    policy_snippets: list[str]
    note: str


class ErrorResponse(BaseModel):
    """Uniform shape for any tool that could not fulfill the request (unknown plan
    or claim id). Keeping errors structured means the model receives a clear,
    validated 'not found' rather than a raw exception string."""
    error: str


# Maps tool name -> the Pydantic model its successful result must satisfy.
RESPONSE_MODELS = {
    "get_plan_details": PlanDetails,
    "get_claim_status": ClaimStatus,
    "estimate_out_of_pocket_cost": CostEstimate,
    "check_coverage": CoverageResult,
}


def validate_tool_result(tool_name, result):
    """Validate a tool's dict result against its Pydantic model, returning a JSON
    string safe to hand back to the model.

    - A dict carrying an "error" key validates as ErrorResponse (expected path for
      unknown plan/claim ids).
    - Otherwise it must satisfy the tool's declared response model.
    - If validation fails, we return a structured error instead of the bad payload,
      so a malformed tool result never reaches the model as if it were valid.
    """
    if isinstance(result, dict) and "error" in result:
        return ErrorResponse(**result).model_dump_json()

    model = RESPONSE_MODELS.get(tool_name)
    if model is None:
        return ErrorResponse(
            error=f"No response model registered for tool {tool_name}."
        ).model_dump_json()

    try:
        return model(**result).model_dump_json()
    except ValidationError as e:
        # The tool returned something that does not match its contract. Do not pass
        # it through — surface a validated error the model can handle safely.
        return ErrorResponse(
            error=(
                f"Tool {tool_name} returned data that failed validation and cannot be "
                f"trusted: {e.error_count()} field error(s). Do not answer from it; "
                f"direct the member to Member Services at 1-800-555-0100."
            )
        ).model_dump_json()


# ---------------------------------------------------------------------------
# SYSTEM PROMPT (see tool_call_log.md for the preamble rationale)
# ---------------------------------------------------------------------------

TOOL_CALLING_PREAMBLE = """You have access to tools that look up live coverage data.

When a member's question needs plan terms, coverage determinations, claim status, or
cost estimates, CALL THE APPROPRIATE TOOL rather than answering from memory. Having no
information in front of you is not a reason to decline — it is the reason to call a
tool. Only answer directly, without a tool, when the question is general
(for example "how do I submit a claim?") or conversational.

Once tool results are returned to you, the rules below apply in full: the tool results
are your context, and you must answer only from them. In particular, if a coverage
determination is "unknown", say it is unknown — do NOT upgrade it to "covered".

---

"""

SYSTEM_PROMPT = TOOL_CALLING_PREAMBLE + PRODUCTION_SYSTEM_PROMPT


# ===========================================================================
# TOOL IMPLEMENTATIONS
# ===========================================================================

def _plan_row(plan_id):
    """Fetch a single plan row as a dict, or None if the plan_id is unknown."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM plans WHERE plan_id = ?", (plan_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_plan_details(plan_id):
    """Return the standard cost-sharing terms for a plan."""
    row = _plan_row(plan_id)
    if row is None:
        return {"error": f"No plan found with id {plan_id}."}
    return {
        "plan_id": row["plan_id"],
        "plan_name": row["plan_name"],
        "monthly_premium": row["monthly_premium"],
        "annual_deductible": row["annual_deductible"],
        "copay_pct": row["copay_pct"],
        "network_tier": row["network_tier"],
    }


def get_claim_status(claim_id):
    """Return the status and details of a claim by id. Parameterized — the id is
    passed straight through as given, never interpolated into SQL text."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM claims WHERE claim_id = ?", (claim_id,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return {"error": f"No claim found with id {claim_id}."}
    return {
        "claim_id": row["claim_id"],
        "status": row["status"],
        "procedure": row["procedure"],
        "claim_amount": row["claim_amount"],
        "plan_id": row["plan_id"],
    }


def estimate_out_of_pocket_cost(procedure, plan_id):
    """Estimate member cost for a procedure from the plan's deductible and copay.

    Deterministic estimate from plan terms, not a real price. Assumes the deductible
    has NOT been met and states that assumption so the model relays it as an estimate.
    """
    row = _plan_row(plan_id)
    if row is None:
        return {"error": f"No plan found with id {plan_id}."}
    deductible = row["annual_deductible"]
    copay_pct = row["copay_pct"]
    return {
        "procedure": procedure,
        "plan_id": plan_id,
        "plan_name": row["plan_name"],
        "annual_deductible": deductible,
        "copay_pct": copay_pct,
        "estimate_note": (
            f"Assuming the ${deductible} annual deductible has not yet been met, the "
            f"member pays the full negotiated cost of '{procedure}' until the deductible "
            f"is reached, then {copay_pct}% coinsurance after that. An exact figure "
            f"requires the negotiated procedure price, which is not in plan records."
        ),
    }


def check_coverage(plan_id, procedure):
    """Check coverage for a procedure by searching the policy text (vector store).

    Honest about the Day 6 gap: the knowledge base has zero exclusions-tagged chunks,
    so this cannot reliably assert 'not covered'. Returns 'likely_covered' or
    'unknown' — never a fabricated denial.
    """
    row = _plan_row(plan_id)
    plan_name = row["plan_name"] if row else plan_id

    chunks = vector_lookup(f"{procedure} coverage {plan_name}", n_results=3)
    snippets = [c["text"] for c in chunks]
    joined = " ".join(snippets).lower()

    proc_l = procedure.lower()
    if proc_l in joined and ("cover" in joined or "covered" in joined):
        determination = "likely_covered"
    else:
        determination = "unknown"

    return {
        "plan_id": plan_id,
        "plan_name": plan_name,
        "procedure": procedure,
        "determination": determination,
        "policy_snippets": snippets,
        "note": (
            "Determination is based only on retrieved policy text. 'unknown' means the "
            "policy text does not clearly address this procedure — it does NOT mean the "
            "service is excluded. The knowledge base has no exclusions data, so coverage "
            "denials cannot be confirmed here; direct the member to Member Services."
        ),
    }


TOOL_DISPATCH = {
    "check_coverage": check_coverage,
    "get_claim_status": get_claim_status,
    "get_plan_details": get_plan_details,
    "estimate_out_of_pocket_cost": estimate_out_of_pocket_cost,
}


# ===========================================================================
# ARGUMENT-PROVENANCE GUARD
#
# The failure this fixes: on "how do I submit a claim?" the model invents a plan
# id (P101) and calls get_plan_details, even though no plan is named. The enum
# guarantees the value is VALID; Pydantic guarantees the result is well-SHAPED;
# neither checks whether the call was WARRANTED. This guard does.
#
# Rule: an identifier-type argument (plan_id, claim_id) must be traceable to the
# member's question — either the id itself appears, or a plan NAME that maps to it
# ("Gold PPO" -> P101). Procedure arguments are free text and not checked here.
# If an id can't be traced, the call is rejected before the tool runs.
# ===========================================================================

# Plan-name -> plan_id, so "Silver plan" in the question justifies plan_id=P102.
PLAN_NAME_HINTS = {
    "P101": ["p101", "gold ppo", "gold"],
    "P102": ["p102", "silver hmo", "silver"],
    "P103": ["p103", "bronze hmo", "bronze"],
}


def check_argument_provenance(tool_name, args, question):
    """Return None if the call is warranted, or a rejection reason string if not.

    Only identifier arguments are checked. A plan_id is warranted if the id or any
    of its name hints appears in the question. A claim_id is warranted if that exact
    id (case-insensitive) appears in the question.
    """
    q = question.lower()

    if "plan_id" in args:
        plan_id = args["plan_id"]
        hints = PLAN_NAME_HINTS.get(plan_id, [plan_id.lower()])
        if not any(h in q for h in hints):
            return (
                f"Rejected {tool_name}: plan_id '{plan_id}' was not named or implied in "
                f"the question. The model appears to have invented it."
            )

    if "claim_id" in args:
        claim_id = args["claim_id"]
        if claim_id.lower() not in q:
            return (
                f"Rejected {tool_name}: claim_id '{claim_id}' does not appear in the "
                f"question."
            )

    return None


# ===========================================================================
# EXECUTION LOOP
# ===========================================================================

def answer_question(question, verbose=True):
    """Full tool-calling loop with Pydantic validation of every tool result."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]

    first = client.chat.completions.create(
        model=GENERATION_MODEL,
        messages=messages,
        tools=TOOLS,
    )
    choice = first.choices[0].message

    if not choice.tool_calls:
        if verbose:
            print("  (no tool call)")
        return {"question": question, "tool_calls": [], "answer": choice.content}

    messages.append(choice)

    executed = []
    for call in choice.tool_calls:
        name = call.function.name
        args = json.loads(call.function.arguments)

        if verbose:
            print(f"  tool call -> {name}({args})")

        # Provenance guard (Step 5): reject calls whose id arguments the model
        # invented rather than drawing from the question. Runs BEFORE the tool.
        rejection = check_argument_provenance(name, args, question)
        if rejection is not None:
            if verbose:
                print(f"    GUARD -> {rejection}")
            raw_result = {"error": rejection}
        else:
            fn = TOOL_DISPATCH.get(name)
            if fn is None:
                raw_result = {"error": f"Unknown tool: {name}"}
            else:
                raw_result = fn(**args)

        # Validate BEFORE returning to the model. This is the Step 4 guarantee.
        validated_json = validate_tool_result(name, raw_result)

        if verbose:
            print(f"    validated -> {validated_json}")

        executed.append({
            "name": name,
            "args": args,
            "rejected": rejection is not None,
            "validated": validated_json,
        })

        messages.append({
            "role": "tool",
            "tool_call_id": call.id,
            "content": validated_json,
        })

    second = client.chat.completions.create(
        model=GENERATION_MODEL,
        messages=messages,
    )
    final = second.choices[0].message.content

    return {"question": question, "tool_calls": executed, "answer": final}


# ===========================================================================
# 5+1 TEST HARNESS
#
# Five questions that should each select a DIFFERENT tool, plus one that should
# select NO tool. "expected_tool = None" means the correct behavior is either no
# tool call at all, or a tool call the provenance guard rejects (both end with the
# model answering the general question without acting on invented data).
# ===========================================================================

TEST_CASES = [
    {
        "question": "What's the monthly premium for the Gold PPO plan?",
        "expected_tool": "get_plan_details",
    },
    {
        "question": "What's the status of claim C1001?",
        "expected_tool": "get_claim_status",
    },
    {
        "question": "Is physical therapy covered under my Silver plan?",
        "expected_tool": "check_coverage",
    },
    {
        "question": "How much would an MRI cost me on the Bronze HMO plan?",
        "expected_tool": "estimate_out_of_pocket_cost",
    },
    {
        # Fifth distinct tool path: a plan-details lookup phrased around deductible
        # rather than premium, to exercise the same tool from a different angle.
        "question": "What's the annual deductible on the Bronze HMO plan?",
        "expected_tool": "get_plan_details",
    },
    {
        # The negative case: general process question, no plan or claim named.
        "question": "How do I submit a claim?",
        "expected_tool": None,
    },
]


def evaluate_case(case):
    """Run one case and decide whether tool selection was correct.

    Correct means:
      - expected_tool set: exactly that tool ran and was NOT rejected by the guard.
      - expected_tool None: either no tool was called, or every attempted call was
        rejected by the provenance guard (so nothing invented reached an answer).
    """
    result = answer_question(case["question"], verbose=True)
    calls = result["tool_calls"]
    expected = case["expected_tool"]

    accepted = [c for c in calls if not c.get("rejected")]
    accepted_names = [c["name"] for c in accepted]

    if expected is None:
        passed = len(accepted) == 0  # nothing invented was acted upon
        selected = "none (correct)" if passed else f"acted on {accepted_names}"
    else:
        passed = accepted_names == [expected]
        selected = accepted_names[0] if accepted_names else "none"

    return {
        "question": case["question"],
        "expected": expected or "none",
        "selected": selected,
        "passed": passed,
        "answer": result["answer"],
        "raw_calls": calls,
    }


def append_audit_entries(results, log_path="tool_call_log.md"):
    """Append a per-tool-call audit entry to the log — Step 6 deliverable.

    One entry per tool call across the harness, capturing which tool ran, what
    arguments were passed, whether the provenance guard rejected it, and what the
    (validated) result was. Timestamped so re-runs append cleanly rather than
    overwriting prior audit trails.
    """
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "\n---\n",
        f"## Tool Call Audit — {stamp}\n",
        "Per-call trail for the 5+1 harness run. Each entry captures the model's tool",
        "choice, the arguments passed, whether the provenance guard accepted the call,",
        "and the validated tool result the model saw on turn 2.\n",
    ]

    for case_num, r in enumerate(results, 1):
        lines.append(f"\n### Case {case_num}: {r['question']}\n")
        if not r["raw_calls"]:
            lines.append("_No tool called (model answered directly)._\n")
            continue
        for call_num, call in enumerate(r["raw_calls"], 1):
            status = "REJECTED (provenance guard)" if call.get("rejected") else "executed"
            lines.append(f"**Call {call_num} — {status}**")
            lines.append(f"- tool: `{call['name']}`")
            lines.append(f"- arguments: `{json.dumps(call['args'])}`")
            lines.append(f"- validated result: `{call['validated']}`\n")

    with open(log_path, "a") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    print("Running 5+1 tool-selection test...\n")

    results = []
    for case in TEST_CASES:
        print(f"{'='*70}\nQUESTION: {case['question']}")
        r = evaluate_case(case)
        mark = "PASS" if r["passed"] else "FAIL"
        print(f"  -> expected: {r['expected']} | selected: {r['selected']} | {mark}\n")
        results.append(r)

    passed = sum(1 for r in results if r["passed"])
    total = len(results)

    # Write the summary results table (Step 5 style).
    lines = [
        "\n---\n",
        "## Step 5 — 5+1 Tool Selection Test\n",
        f"**Result: {passed}/{total} correct tool selection.**\n",
        "| # | Question | Expected | Selected | Pass |",
        "|---|---|---|---|---|",
    ]
    for i, r in enumerate(results, 1):
        mark = "✅" if r["passed"] else "❌"
        lines.append(
            f"| {i} | {r['question']} | `{r['expected']}` | `{r['selected']}` | {mark} |"
        )

    with open("tool_call_log.md", "a") as f:
        f.write("\n".join(lines) + "\n")

    # Step 6: per-call audit trail for debugging and future review.
    append_audit_entries(results)

    print(f"{'='*70}")
    print(f"RESULT: {passed}/{total} correct.")
    print("Appended summary table AND per-call audit to tool_call_log.md")
