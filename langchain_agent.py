"""
Day 21 — Agentic Frameworks: LangChain Agents & Tool Use.

Turns the Day 13 function-calling tools (check_coverage, get_claim_status,
get_plan_details) into a LangChain ReAct agent, and captures its reasoning
traces (Thought -> Action -> Observation -> ... -> Final Answer).

API note: this project's LangChain version (1.3.14 / langgraph 1.2.10) has
moved the ReAct agent constructor to langgraph.prebuilt.create_react_agent —
the older langchain.agents.create_react_agent / AgentExecutor path used by
most tutorials no longer exists in this version. Tools are defined with the
@tool decorator from langchain_core.tools (also moved from langchain.tools).

Model note: uses llama3.1:8b via ChatOpenAI pointed at the local Ollama
server — same model Day 13's tool_calling_chatbot.py uses, since it's the
only local model that reliably emits structured tool_calls (see
tool_call_log.md).

langgraph's create_react_agent has no verbose=True flag like the old
AgentExecutor. Instead it returns the full message history (including tool
call requests and their results), which we format ourselves into a
Thought/Action/Observation trace to get equivalent visibility.
"""

import os

from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from tool_calling_chatbot import check_coverage, get_claim_status, get_plan_details

load_dotenv()

# ---------------------------------------------------------------------------
# LangChain tool wrappers around the Day 13 functions
#
# The @tool decorator derives the tool's name from the function name and its
# description from the docstring — the description is what the agent reads
# to decide WHEN to call a tool, so these are written the same way Day 13's
# JSON schema descriptions were: explicit about what the tool is for and when
# to use it, not just what it does mechanically.
# ---------------------------------------------------------------------------

@tool
def check_coverage_tool(plan_id: str, procedure: str) -> dict:
    """Check whether a specific medical procedure or service is covered under
    a given health plan. Use this when the member asks whether something is
    covered, included, or paid for — e.g. 'is physical therapy covered on my
    Silver plan?'. plan_id must be one of P101 (Gold PPO), P102 (Silver HMO),
    P103 (Bronze HMO). Returns a coverage determination, not a cost estimate.
    """
    return check_coverage(plan_id, procedure)


@tool
def get_claim_status_tool(claim_id: str) -> dict:
    """Look up the current processing status of a submitted claim by its
    claim ID. Use this when the member asks about a specific claim — its
    status, whether it was approved or denied, or what happened to it.
    Requires an actual claim ID stated by the member (e.g. 'C1001') — do not
    call this if no claim ID was given.
    """
    return get_claim_status(claim_id)


@tool
def get_plan_details_tool(plan_id: str) -> dict:
    """Retrieve the standard terms of a health plan: monthly premium, annual
    deductible, copay percentage, and network tier. Use this for questions
    about what a plan costs or how its cost-sharing works. plan_id must be
    one of P101 (Gold PPO), P102 (Silver HMO), P103 (Bronze HMO). Does not
    say whether any particular procedure is covered — use check_coverage_tool
    for that.
    """
    return get_plan_details(plan_id)


TOOLS = [check_coverage_tool, get_claim_status_tool, get_plan_details_tool]

# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

llm = ChatOpenAI(
    model="llama3.1:8b",
    base_url=os.environ["OLLAMA_BASE_URL"],
    api_key=os.environ["OLLAMA_API_KEY"],
)

AGENT_SYSTEM_PROMPT = """You are a healthcare coverage assistant helping members
understand their health plans. You have access to tools that look up live
coverage data — use them whenever a question needs plan terms, coverage
determinations, or claim status. Only answer directly, without a tool, when
the question is general (e.g. "how do I submit a claim?") or conversational.
Keep answers concise and factual."""

agent = create_react_agent(llm, TOOLS, prompt=AGENT_SYSTEM_PROMPT)


def format_trace(messages) -> str:
    """Format a langgraph message list into a readable
    Thought -> Action -> Observation -> ... -> Final Answer trace.

    langgraph's create_react_agent returns the full message history rather
    than a verbose=True console log, so this reconstructs an equivalent
    trace: each AIMessage with tool_calls becomes an "Action" (the model's
    own reasoning text, if any, printed as "Thought"), each ToolMessage
    becomes an "Observation", and the final AIMessage with no tool_calls is
    the "Final Answer".
    """
    lines = []
    for msg in messages:
        msg_type = type(msg).__name__

        if msg_type == "HumanMessage":
            continue  # the question itself, printed separately by the caller

        elif msg_type == "AIMessage":
            tool_calls = getattr(msg, "tool_calls", None) or []
            if tool_calls:
                if msg.content:
                    lines.append(f"Thought: {msg.content}")
                for call in tool_calls:
                    lines.append(f"Action: {call['name']}({call['args']})")
            else:
                lines.append(f"Final Answer: {msg.content}")

        elif msg_type == "ToolMessage":
            lines.append(f"Observation: {msg.content}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 5 test questions
# ---------------------------------------------------------------------------

TEST_QUESTIONS = [
    "What's the status of claim C1001?",
    "Is physical therapy covered under my Silver plan?",
    "What's the monthly premium for the Gold PPO plan?",
    "How do I submit a claim?",
    "What's the annual deductible on the Bronze HMO plan?",
]

# Step 5: what a human coverage-support rep would reasonably do for each
# question, written BEFORE running the agent so this isn't retrofitted to
# match whatever the agent happened to do.
HUMAN_REP_EXPECTATION = {
    "What's the status of claim C1001?":
        "Look up the claim by ID — a rep would pull up the claim record directly.",
    "Is physical therapy covered under my Silver plan?":
        "Check the Silver plan's coverage rules for physical therapy — a rep "
        "would consult the plan's benefit summary.",
    "What's the monthly premium for the Gold PPO plan?":
        "Look up the Gold PPO plan's standard terms — a rep would pull plan "
        "details, not a claim or a coverage determination.",
    "How do I submit a claim?":
        "Answer from general process knowledge — a rep would explain the "
        "submission steps without looking up any specific member's plan or "
        "claim data, since none was named.",
    "What's the annual deductible on the Bronze HMO plan?":
        "Look up the Bronze HMO plan's standard terms — same as the premium "
        "question, just a different field.",
}


def run_test():
    results = []
    for i, question in enumerate(TEST_QUESTIONS, start=1):
        print(f"{'='*70}\n[{i}/5] {question}")
        result = agent.invoke({"messages": [{"role": "user", "content": question}]})
        messages = result["messages"]
        trace = format_trace(messages)
        print(trace)
        print()

        tool_calls_made = [
            call["name"]
            for msg in messages
            if type(msg).__name__ == "AIMessage"
            for call in (getattr(msg, "tool_calls", None) or [])
        ]

        results.append({
            "question": question,
            "trace": trace,
            "tool_calls_made": tool_calls_made,
            "human_expectation": HUMAN_REP_EXPECTATION[question],
        })

    return results


def write_report(results):
    lines = [
        "# Day 21 — LangChain ReAct Agent Traces\n",
        "5 test questions run through a `langgraph.prebuilt.create_react_agent` "
        "wrapping the Day 13 tools (`check_coverage`, `get_claim_status`, "
        "`get_plan_details`) as LangChain `@tool`-decorated functions. Model: "
        "`llama3.1:8b` via `ChatOpenAI` pointed at the local Ollama server — "
        "same model Day 13 uses for tool calling.\n",
        "**API note:** this LangChain version (1.3.14) no longer has "
        "`langchain.agents.create_react_agent` / `AgentExecutor` — the ReAct "
        "agent now lives in `langgraph.prebuilt.create_react_agent`, and it has "
        "no `verbose=True` console log. Instead it returns the full message "
        "history, which is reformatted below into an equivalent "
        "Thought -> Action -> Observation -> Final Answer trace.\n",
    ]

    for i, r in enumerate(results, 1):
        lines.append(f"## Q{i}: {r['question']}\n")
        lines.append(f"**Tool(s) called:** {r['tool_calls_made'] or 'none'}\n")
        lines.append(f"**Human coverage-support rep would:** {r['human_expectation']}\n")
        lines.append("**Reasoning trace:**\n")
        lines.append("```")
        lines.append(r["trace"])
        lines.append("```\n")

    lines.append("## Step 5 — Tool-selection quality comparison\n")
    lines.append(
        "| # | Question | Tool(s) called | Matches human rep expectation? |"
    )
    lines.append("|---|---|---|---|")
    for i, r in enumerate(results, 1):
        lines.append(
            f"| {i} | {r['question']} | {r['tool_calls_made'] or 'none'} | *(fill in after review)* |"
        )

    with open("agent_traces.md", "w") as f:
        f.write("\n".join(lines))
    print("Wrote agent_traces.md")


if __name__ == "__main__":
    results = run_test()
    write_report(results)
