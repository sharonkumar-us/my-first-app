"""
Day 23 — Model Context Protocol (MCP) server.

Exposes this project's coverage and claims lookups as MCP tools, so any MCP
client (Claude Desktop, Cline) can call them directly rather than going
through this project's own FastAPI backend or Streamlit UI.

API note: this project's installed MCP SDK (mcp==2.0.0) uses
mcp.server.MCPServer, not the mcp.server.fastmcp.FastMCP class most MCP
tutorials reference (that's the 1.x API). The decorator usage
(@mcp.tool()) is the same idiom either way, just imported from a different
path in this version.

Both tools below are thin wrappers around functions already built and
tested in tool_calling_chatbot.py (Day 13) — check_coverage() already
calls Day 10's vector_lookup() plus the Day 4 plans table, matching what
the portal's Step 2 describes, so nothing is reimplemented here.
"""

from mcp.server import MCPServer

from tool_calling_chatbot import check_coverage, get_claim_status

mcp = MCPServer(
    name="coverage-chatbot",
    description=(
        "Healthcare coverage chatbot tools: check whether a procedure is "
        "covered under a plan, and look up claim status. Synthetic training "
        "data only, not a real insurance product."
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


if __name__ == "__main__":
    mcp.run(transport="stdio")
