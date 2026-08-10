"""
Day 22 -> Day 24 — Multi-Agent Orchestration, now with MCP tools, memory, and
resilience.

Day 22: Router + Coverage/Claims specialists wired via LangGraph, calling
        Day 13's tool functions directly (in-process Python calls).
Day 24 Step 1: tool calls now go through the Day 23 MCP server
               (mcp_server.py) as a real client, over stdio.
Day 24 Step 2: specialists now receive conversation memory (last N turns +
               inferred plan_id) from Day 20's SQLite-backed memory store,
               imported directly from coverage-chatbot-api/main.py.
Day 24 Step 3-4: every MCP tool call is wrapped in asyncio.wait_for with a
               10s timeout, one retry on failure, then a canned fallback.

DESIGN CHANGE FROM THE FIRST DAY 24 DRAFT: the first version of this file
asked the LLM to decide, in free text, whether it needed a tool and which
one. Testing against the real 5-question set showed this was unreliable —
llama3.1:8b answered from its own general insurance knowledge instead of
calling any tool on every single question, producing entirely fabricated
numbers (a $20 copay, a $405.92 premium, a $3,000/$6,000 deductible split —
none of which exist in this project's data). This reproduces the same
"trusting LLM judgment on tool necessity" failure Day 13's
check_argument_provenance() guard exists to prevent.

FIX: tool selection is now fully deterministic, matching the pattern already
used elsewhere in this project (Day 19's _try_build_cards, Day 20's
_infer_plan_id) — regex/keyword matching decides whether a tool is needed
and with what arguments. The LLM is used ONLY to phrase the final sentence
from real tool output; it is never asked whether to call a tool at all.
"""

import asyncio
import os
import re
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Literal, TypedDict

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

load_dotenv(Path(__file__).resolve().parent / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent / "coverage-chatbot-api"))
from main import _load_history, _infer_plan_id  # noqa: E402

llm = ChatOpenAI(
    model="llama3.1:8b",
    base_url=os.environ["OLLAMA_BASE_URL"],
    api_key=os.environ["OLLAMA_API_KEY"],
)

TIMEOUT_SECONDS = 10
MAX_RETRIES = 1
FALLBACK_MESSAGE = (
    "I'm having trouble accessing that right now, please contact member support."
)

MCP_SERVER_PARAMS = StdioServerParameters(
    command=str(Path(__file__).resolve().parent / ".venv" / "bin" / "python"),
    args=[str(Path(__file__).resolve().parent / "mcp_server.py")],
)


# ---------------------------------------------------------------------------
# Resilient MCP client wrapper — Day 24 Steps 3-4
# ---------------------------------------------------------------------------

class MCPToolClient:
    """Owns one stdio connection to mcp_server.py for the lifetime of a run."""

    def __init__(self):
        self._stack = AsyncExitStack()
        self.session: ClientSession | None = None

    async def __aenter__(self):
        read, write = await self._stack.enter_async_context(stdio_client(MCP_SERVER_PARAMS))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
        return self

    async def __aexit__(self, *exc):
        await self._stack.aclose()

    async def _call_once(self, tool_name: str, arguments: dict) -> str:
        result = await asyncio.wait_for(
            self.session.call_tool(tool_name, arguments),
            timeout=TIMEOUT_SECONDS,
        )
        return result.content[0].text if result.content else "{}"

    async def call_tool_resilient(self, tool_name: str, arguments: dict) -> tuple[str, bool]:
        """Call an MCP tool with a 10s timeout and one retry on failure.

        Returns (result_text, used_fallback).
        """
        last_error = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                text = await self._call_once(tool_name, arguments)
                return text, False
            except Exception as e:
                last_error = e
                if attempt < MAX_RETRIES:
                    continue
        print(f"  [MCP call failed after {MAX_RETRIES + 1} attempt(s)]: {last_error}")
        return FALLBACK_MESSAGE, True


# ---------------------------------------------------------------------------
# Deterministic tool selection — Day 24 fix
#
# No LLM judgment on WHETHER to call a tool. Regex/keyword matching only,
# same pattern as _try_build_cards (Day 19) and _infer_plan_id (Day 20).
# ---------------------------------------------------------------------------

PLAN_TERM_KEYWORDS = ("premium", "deductible", "copay", "network tier", "network")
CLAIM_ID_PATTERN = re.compile(r"\b(C\d{4})\b", re.IGNORECASE)


async def answer_claims_question(
    question: str, mcp_client: MCPToolClient, trace: list[str]
) -> str:
    """Claims Specialist: deterministic — a claim ID must be present in the
    question itself (memory does not carry claim IDs forward, only plan
    context, matching Day 20's actual scope)."""
    match = CLAIM_ID_PATTERN.search(question)
    if not match:
        answer = (
            "I don't see a claim ID in your question. Could you provide the "
            "claim ID (e.g. 'C1001') so I can look up its status?"
        )
        trace.append(f"  [No claim ID found — no tool called] Final Answer: {answer}")
        return answer

    claim_id = match.group(1).upper()
    trace.append(f"  Action: get_claim_status_tool({{'claim_id': '{claim_id}'}})")
    result_text, used_fallback = await mcp_client.call_tool_resilient(
        "get_claim_status_tool", {"claim_id": claim_id}
    )
    trace.append(f"  Observation: {result_text}" + (" [FALLBACK USED]" if used_fallback else ""))

    if used_fallback:
        return result_text

    final_prompt = f"""You are the Claims Specialist for a healthcare coverage
assistant. Give a concise final answer to the member's question using ONLY
this tool result — do not add information not present in it.

Member question: {question}

Tool result: {result_text}"""
    answer = llm.invoke([{"role": "user", "content": final_prompt}]).content.strip()
    trace.append(f"  Final Answer: {answer}")
    return answer


async def answer_coverage_question(
    question: str,
    plan_id: str | None,
    plan_name: str | None,
    mcp_client: MCPToolClient,
    trace: list[str],
) -> str:
    """Coverage Specialist: deterministic — plan_id comes from the current
    question or conversation memory (already inferred by the caller). Tool
    choice is keyword-based: plan-terms keywords -> get_plan_details_tool,
    otherwise treat it as a coverage-determination question ->
    check_coverage_tool. No plan at all -> honest refusal, no tool call."""
    if not plan_id:
        answer = (
            "I don't see which plan you're asking about. Could you let me "
            "know the plan name (Gold PPO, Silver HMO, or Bronze HMO)?"
        )
        trace.append(f"  [No plan established — no tool called] Final Answer: {answer}")
        return answer

    q_lower = question.lower()
    is_plan_terms_question = any(kw in q_lower for kw in PLAN_TERM_KEYWORDS)

    if is_plan_terms_question:
        trace.append(f"  Action: get_plan_details_tool({{'plan_id': '{plan_id}'}})")
        result_text, used_fallback = await mcp_client.call_tool_resilient(
            "get_plan_details_tool", {"plan_id": plan_id}
        )
    else:
        # Extract a rough "procedure" — everything after common lead-in
        # phrases, falling back to the question itself. Good enough for
        # this project's tool, which does its own retrieval matching.
        procedure = re.sub(
            r"^(is|does|do you|would|will)\s+", "", question, flags=re.IGNORECASE
        ).strip("?. ")
        trace.append(
            f"  Action: check_coverage_tool({{'plan_id': '{plan_id}', 'procedure': '{procedure}'}})"
        )
        result_text, used_fallback = await mcp_client.call_tool_resilient(
            "check_coverage_tool", {"plan_id": plan_id, "procedure": procedure}
        )

    trace.append(f"  Observation: {result_text}" + (" [FALLBACK USED]" if used_fallback else ""))

    if used_fallback:
        return result_text

    final_prompt = f"""You are the Coverage Specialist for a healthcare
coverage assistant. Give a concise final answer to the member's question
using ONLY this tool result — do not add information not present in it. If
the tool result shows a coverage determination of "unknown", say clearly
that you cannot confirm coverage either way — never say "likely covered."

Member question: {question}

Tool result: {result_text}"""
    answer = llm.invoke([{"role": "user", "content": final_prompt}]).content.strip()
    trace.append(f"  Final Answer: {answer}")
    return answer


# ---------------------------------------------------------------------------
# Router — unchanged from Day 22, no tools, no MCP involvement
# ---------------------------------------------------------------------------

ROUTER_PROMPT = """You are a routing classifier for a healthcare coverage
chatbot. Classify the member's question into EXACTLY ONE category:
- "coverage": questions about whether a procedure is covered, plan terms
  (premium, deductible, copay, network tier), or enrollment requirements
- "claims": questions about a specific claim's status, amount, or processing

Respond with ONLY one word: coverage or claims. Do not explain your answer."""


def classify_question(question: str) -> Literal["coverage", "claims"]:
    response = llm.invoke([
        {"role": "system", "content": ROUTER_PROMPT},
        {"role": "user", "content": question},
    ])
    label = response.content.strip().lower()
    if "claim" in label:
        return "claims"
    return "coverage"


# ---------------------------------------------------------------------------
# Graph state + nodes
# ---------------------------------------------------------------------------

class GraphState(TypedDict):
    session_id: str
    question: str
    route: str
    answer: str
    trace: list[str]


def make_graph(mcp_client: MCPToolClient):
    async def router_node(state: GraphState) -> GraphState:
        route = classify_question(state["question"])
        trace = state.get("trace", [])
        trace.append(f"[Router] classified as: {route}")
        return {**state, "route": route, "trace": trace}

    async def coverage_node(state: GraphState) -> GraphState:
        trace = state.get("trace", [])
        trace.append("[Coverage Specialist] invoked")

        raw_history, _ph, _tb, _ta = _load_history(state["session_id"])
        plan_id, plan_name = _infer_plan_id(state["question"], raw_history)
        trace.append(f"  [Memory] inferred plan: {plan_name or 'none'}")

        answer = await answer_coverage_question(
            state["question"], plan_id, plan_name, mcp_client, trace
        )
        return {**state, "answer": answer, "trace": trace}

    async def claims_node(state: GraphState) -> GraphState:
        trace = state.get("trace", [])
        trace.append("[Claims Specialist] invoked")

        raw_history, _ph, _tb, _ta = _load_history(state["session_id"])
        _plan_id, plan_name = _infer_plan_id(state["question"], raw_history)
        trace.append(f"  [Memory] inferred plan: {plan_name or 'none'}")

        answer = await answer_claims_question(state["question"], mcp_client, trace)
        return {**state, "answer": answer, "trace": trace}

    def route_decision(state: GraphState) -> str:
        return state["route"]

    builder = StateGraph(GraphState)
    builder.add_node("router", router_node)
    builder.add_node("coverage", coverage_node)
    builder.add_node("claims", claims_node)
    builder.add_edge(START, "router")
    builder.add_conditional_edges(
        "router", route_decision, {"coverage": "coverage", "claims": "claims"}
    )
    builder.add_edge("coverage", END)
    builder.add_edge("claims", END)
    return builder.compile()


async def run_question(session_id: str, question: str, mcp_client: MCPToolClient) -> dict:
    graph = make_graph(mcp_client)
    result = await graph.ainvoke({
        "session_id": session_id,
        "question": question,
        "route": "",
        "answer": "",
        "trace": [],
    })
    return result


# ---------------------------------------------------------------------------
# Same 5 test questions as Day 21/22, for a direct comparison
# ---------------------------------------------------------------------------

TEST_QUESTIONS = [
    "What's the status of claim C1001?",
    "Is physical therapy covered under my Silver plan?",
    "What's the monthly premium for the Gold PPO plan?",
    "How do I submit a claim?",
    "What's the annual deductible on the Bronze HMO plan?",
]


async def run_test():
    import uuid
    session_id = str(uuid.uuid4())
    results = []
    async with MCPToolClient() as mcp_client:
        for i, question in enumerate(TEST_QUESTIONS, start=1):
            print(f"{'='*70}\n[{i}/5] {question}")
            result = await run_question(session_id, question, mcp_client)
            for line in result["trace"]:
                print(line)
            print()
            results.append({
                "question": question,
                "route": result["route"],
                "answer": result["answer"],
                "trace": result["trace"],
            })
    return results


if __name__ == "__main__":
    asyncio.run(run_test())
