"""
Day 23 — Model Context Protocol (MCP) server.
Day 24 — added get_plan_details_tool (genuinely missing capability
         discovered during Day 24 integration testing: the Day 22/24
         multi-agent workflow needs premium/deductible/copay lookups, which
         this server didn't expose until now).

Exposes this project's coverage, claims, and plan-detail lookups as MCP
tools, so any MCP client (Claude Desktop, Cline, or this project's own
multi_agent.py) can call them directly.

API note: this project's installed MCP SDK (mcp==2.0.0) uses
mcp.server.MCPServer, not the mcp.server.fastmcp.FastMCP class most MCP
tutorials reference (that's the 1.x API).

All three tools below are thin wrappers around functions already built and
tested in tool_calling_chatbot.py (Day 13).
"""

from mcp.server import MCPServer

from tool_calling_chatbot import check_coverage, get_claim_status, get_plan_details

mcp = MCPServer(
    name="coverage-chatbot",
    description=(
        "Healthcare coverage chatbot tools: check whether a procedure is "
        "covered under a plan, look up claim status, and retrieve plan "
        "terms (premium, deductible, copay, network tier). Synthetic "
        "training data only, not a real insurance product."
    ),
)


@mcp.tool()
def check_coverage_tool(plan_id: str, procedure: str) -> dict:
    """Check whether a specific medical procedure or service is covered
    under a given health plan. plan_id must be one of P101 (Gold PPO),
    P102 (Silver HMO), P103 (Bronze HMO). Returns a coverage determination
    based on retrieved policy text, not a cost estimate."""
    return check_coverage(plan_id, procedure)


@mcp.tool()
def get_claim_status_tool(claim_id: str) -> dict:
    """Look up the current processing status of a submitted claim by its
    claim ID (e.g. 'C1001'). Returns status, procedure, claim amount, and
    the associated plan ID."""
    return get_claim_status(claim_id)


@mcp.tool()
def get_plan_details_tool(plan_id: str) -> dict:
    """Retrieve the standard terms of a health plan: monthly premium,
    annual deductible, copay percentage, and network tier. plan_id must be
    one of P101 (Gold PPO), P102 (Silver HMO), P103 (Bronze HMO)."""
    return get_plan_details(plan_id)


if __name__ == "__main__":
    mcp.run(transport="stdio")
