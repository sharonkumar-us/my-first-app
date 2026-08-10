"""
Day 22 — Multi-Agent Orchestration.

Splits the Day 21 single ReAct agent into three roles wired together via a
LangGraph StateGraph:
  - Router: classifies the question as coverage, claims, or enrollment
  - Coverage Specialist: handles coverage AND enrollment questions (both use
    check_coverage_tool / get_plan_details_tool / retrieval — there's no
    dedicated "enrollment" tool in this project, and enrollment info lives in
    the same RAG/vector store the Coverage Specialist already has access to,
    per raw_text/faq.txt from Day 5)
  - Claims Specialist: handles claims questions (get_claim_status_tool)

This is a genuinely different code path from Day 21's create_react_agent —
that used a pre-built ReAct loop; this builds the graph by hand (StateGraph,
add_node, add_conditional_edges) so the Router's classification explicitly
decides which specialist node runs, rather than one agent deciding among all
tools itself.

Model note: llama3.1:8b via ChatOpenAI pointed at local Ollama, same as
Day 21 — the only local model that reliably emits structured tool_calls.
"""

import os
from typing import Literal, TypedDict

from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import create_react_agent

from tool_calling_chatbot import check_coverage, get_claim_status, get_plan_details

load_dotenv()

llm = ChatOpenAI(
    model="llama3.1:8b",
    base_url=os.environ["OLLAMA_BASE_URL"],
    api_key=os.environ["OLLAMA_API_KEY"],
)

# ---------------------------------------------------------------------------
# Tools (same wrappers as Day 21's langchain_agent.py, duplicated here rather
# than imported so this file's specialists are self-contained and Day 21's
# file is untouched)
# ---------------------------------------------------------------------------

@tool
def check_coverage_tool(plan_id: str, procedure: str) -> dict:
    """Check whether a specific medical procedure or service is covered under
    a given health plan. plan_id must be one of P101 (Gold PPO), P102 (Silver
    HMO), P103 (Bronze HMO)."""
    return check_coverage(plan_id, procedure)


@tool
def get_claim_status_tool(claim_id: str) -> dict:
    """Look up the current processing status of a submitted claim by its
    claim ID (e.g. 'C1001')."""
    return get_claim_status(claim_id)


@tool
def get_plan_details_tool(plan_id: str) -> dict:
    """Retrieve the standard terms of a health plan: monthly premium, annual
    deductible, copay percentage, and network tier. plan_id must be one of
    P101 (Gold PPO), P102 (Silver HMO), P103 (Bronze HMO)."""
    return get_plan_details(plan_id)


# ---------------------------------------------------------------------------
# Specialist agents — each a small ReAct agent scoped to its own tool subset
# ---------------------------------------------------------------------------

COVERAGE_SPECIALIST_PROMPT = """You are the Coverage Specialist for a
healthcare coverage assistant. You handle questions about plan coverage,
plan terms (premium, deductible, copay, network tier), and enrollment
requirements. Use your tools to look up real data — do not guess. If the
question is about a specific claim's status, say that's outside your scope
(a Claims Specialist handles that)."""

coverage_specialist = create_react_agent(
    llm,
    [check_coverage_tool, get_plan_details_tool],
    prompt=COVERAGE_SPECIALIST_PROMPT,
)

CLAIMS_SPECIALIST_PROMPT = """You are the Claims Specialist for a healthcare
coverage assistant. You handle questions about claim status, claim amounts,
and claim processing. Use your tools to look up real data — do not guess. If
the question is about plan coverage or plan terms rather than a specific
claim, say that's outside your scope (a Coverage Specialist handles that)."""

claims_specialist = create_react_agent(
    llm,
    [get_claim_status_tool],
    prompt=CLAIMS_SPECIALIST_PROMPT,
)


# ---------------------------------------------------------------------------
# Router — classifies the question, no tools of its own
# ---------------------------------------------------------------------------

ROUTER_PROMPT = """You are a routing classifier for a healthcare coverage
chatbot. Classify the member's question into EXACTLY ONE category:
- "coverage": questions about whether a procedure is covered, plan terms
  (premium, deductible, copay, network tier), or enrollment requirements
- "claims": questions about a specific claim's status, amount, or processing

Respond with ONLY one word: coverage or claims. Do not explain your answer."""


def classify_question(question: str) -> Literal["coverage", "claims"]:
    """Call the router LLM directly (no tools, no agent loop needed — this
    is a single classification call, not a multi-step reasoning task)."""
    response = llm.invoke([
        {"role": "system", "content": ROUTER_PROMPT},
        {"role": "user", "content": question},
    ])
    label = response.content.strip().lower()
    if "claim" in label:
        return "claims"
    return "coverage"  # default / covers "coverage" and "enrollment" alike


# ---------------------------------------------------------------------------
# Graph state + nodes
# ---------------------------------------------------------------------------

class GraphState(TypedDict):
    question: str
    route: str
    answer: str
    trace: list[str]


def router_node(state: GraphState) -> GraphState:
    route = classify_question(state["question"])
    trace = state.get("trace", [])
    trace.append(f"[Router] classified as: {route}")
    return {**state, "route": route, "trace": trace}


def coverage_node(state: GraphState) -> GraphState:
    trace = state.get("trace", [])
    trace.append("[Coverage Specialist] invoked")
    result = coverage_specialist.invoke(
        {"messages": [{"role": "user", "content": state["question"]}]}
    )
    final_message = result["messages"][-1]
    for msg in result["messages"]:
        msg_type = type(msg).__name__
        if msg_type == "AIMessage":
            tool_calls = getattr(msg, "tool_calls", None) or []
            for call in tool_calls:
                trace.append(f"  Action: {call['name']}({call['args']})")
        elif msg_type == "ToolMessage":
            trace.append(f"  Observation: {msg.content}")
    trace.append(f"  Final Answer: {final_message.content}")
    return {**state, "answer": final_message.content, "trace": trace}


def claims_node(state: GraphState) -> GraphState:
    trace = state.get("trace", [])
    trace.append("[Claims Specialist] invoked")
    result = claims_specialist.invoke(
        {"messages": [{"role": "user", "content": state["question"]}]}
    )
    final_message = result["messages"][-1]
    for msg in result["messages"]:
        msg_type = type(msg).__name__
        if msg_type == "AIMessage":
            tool_calls = getattr(msg, "tool_calls", None) or []
            for call in tool_calls:
                trace.append(f"  Action: {call['name']}({call['args']})")
        elif msg_type == "ToolMessage":
            trace.append(f"  Observation: {msg.content}")
    trace.append(f"  Final Answer: {final_message.content}")
    return {**state, "answer": final_message.content, "trace": trace}


def route_decision(state: GraphState) -> str:
    """Conditional edge function: reads the route the router_node set and
    tells the graph which specialist node to go to next."""
    return state["route"]


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

builder = StateGraph(GraphState)
builder.add_node("router", router_node)
builder.add_node("coverage", coverage_node)
builder.add_node("claims", claims_node)

builder.add_edge(START, "router")
builder.add_conditional_edges(
    "router",
    route_decision,
    {"coverage": "coverage", "claims": "claims"},
)
builder.add_edge("coverage", END)
builder.add_edge("claims", END)

graph = builder.compile()


def run_question(question: str) -> dict:
    """Run one question through the full router -> specialist graph."""
    result = graph.invoke({"question": question, "route": "", "answer": "", "trace": []})
    return result


# ---------------------------------------------------------------------------
# Same 5 test questions as Day 21, for a direct comparison
# ---------------------------------------------------------------------------

TEST_QUESTIONS = [
    "What's the status of claim C1001?",
    "Is physical therapy covered under my Silver plan?",
    "What's the monthly premium for the Gold PPO plan?",
    "How do I submit a claim?",
    "What's the annual deductible on the Bronze HMO plan?",
]


def run_test():
    results = []
    for i, question in enumerate(TEST_QUESTIONS, start=1):
        print(f"{'='*70}\n[{i}/5] {question}")
        result = run_question(question)
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
    run_test()
