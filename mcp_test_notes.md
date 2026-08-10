# Day 23 — MCP Server Test Notes

Exposed two Day 13 tools (check_coverage, get_claim_status) as an MCP server
(mcp_server.py) and registered it with Claude Desktop via
claude_desktop_config.json. Both tools confirmed working end-to-end through
Claude Desktop's own UI.

**SDK version note:** this project's installed MCP SDK is mcp==2.0.0, which
uses mcp.server.MCPServer rather than the mcp.server.fastmcp.FastMCP class
most MCP tutorials reference (that's the 1.x API). The @mcp.tool() decorator
usage is the same idiom either way, just imported from a different path in
this version.

---

## Registration

Added an mcpServers entry to
~/Library/Application Support/Claude/claude_desktop_config.json (backed up
first as claude_desktop_config.json.backup before editing, since the file
already contained substantial existing Claude Desktop app settings that
needed to be preserved, not overwritten):

    "mcpServers": {
      "coverage-chatbot": {
        "command": "/Users/sharonkumar/projects/my-first-app/.venv/bin/python",
        "args": ["/Users/sharonkumar/projects/my-first-app/mcp_server.py"]
      }
    }

Full absolute paths were required for both the interpreter and the script —
Claude Desktop launches the subprocess directly, it does not activate a venv
or cd into the project directory first.

---

## Bug found: relative file paths break when launched outside the project dir

First registration attempt failed with "Server disconnected" in Claude
Desktop's connector panel. Viewing the logs showed the actual Python
traceback:

    chromadb.errors.InternalError: Read-only file system (os error 30)

**Root cause:** retrieval_engine.py initialized Chroma with a relative path
(chromadb.PersistentClient(path="./chroma_data")). This worked fine every
other time this project's code has run, because it was always launched from
the project root (terminal, uvicorn --app-dir). Claude Desktop launches the
MCP server subprocess from a different working directory, so "./chroma_data"
resolved to a path outside the project that Claude Desktop couldn't write to.

**This turned out to be one instance of a broader pattern** — three separate
files had the same relative-path assumption baked in:

1. retrieval_engine.py — chromadb.PersistentClient(path="./chroma_data")
2. retrieval_engine.py — sqlite3.connect("coverage.db") inside sql_lookup()
3. tool_calling_chatbot.py — DB_PATH = "coverage.db"
4. rag_chatbot.py — load_dotenv() with no path, meaning it only found .env
   when the working directory happened to already be the project root

Testing method: rather than repeatedly registering/restarting Claude Desktop
to catch each new error one at a time, later bugs were found faster by
simulating Claude Desktop's launch conditions directly in the terminal —
running the exact same interpreter and script path from `/` (root directory)
instead of the project folder, which reproduces the same working-directory
mismatch without needing a full Claude Desktop restart cycle each time.

**Fix applied to all four:** anchor every relative path to the file's own
location using pathlib, e.g.:

    from pathlib import Path
    DB_PATH = str(Path(__file__).resolve().parent / "coverage.db")

and for load_dotenv():

    load_dotenv(Path(__file__).resolve().parent / ".env")

This makes every path absolute and independent of whatever directory the
script happens to be launched from — a real correctness fix that also
protects any FUTURE code that imports these modules from a different working
directory, not just this MCP server.

Verified the fix by running the same import + function calls from `/`
directly (bypassing Claude Desktop entirely) before re-testing through the
actual app, to get a faster feedback loop:

    cd /
    /Users/sharonkumar/projects/my-first-app/.venv/bin/python -c "
    import sys
    sys.path.insert(0, '/Users/sharonkumar/projects/my-first-app')
    from tool_calling_chatbot import check_coverage, get_claim_status
    print(get_claim_status('C1001'))
    print(check_coverage('P102', 'physical therapy'))
    "

Both calls returned correct real data with no path errors, confirming the
fix before going back to Claude Desktop.

---

## Test 1: check_coverage_tool

**Question asked in Claude Desktop:** "Is physical therapy covered under the
Silver HMO plan?"

**Result:** PASS. Claude Desktop's UI showed "Loaded tools, used
coverage-chatbot integration," confirming the MCP tool call happened. The
response correctly reported the Silver HMO plan's real terms ($300/month
premium, $1,500 annual deductible, 20% copay, Silver network tier — matches
data/plans.csv exactly) and handled the "unknown" coverage determination
honestly, explicitly stating it could not confirm physical therapy coverage
one way or the other rather than guessing — arguably tighter discipline
around an "unknown" result than either Day 21's or Day 22's own agent
prompts showed on the same underlying tool output.

---

## Test 2: get_claim_status_tool

**Question asked in Claude Desktop:** "What's the status of claim C1001?"

**Result:** PASS. Correct data returned: status Pending, procedure X-ray,
amount $250, plan P101 (Gold PPO). Claude Desktop also proactively noted
that this claim belongs to the Gold PPO plan, not the Silver HMO plan
discussed in Test 1, and flagged the mismatch in case that wasn't the
claim intended — a genuinely useful piece of reasoning the tool output
itself didn't request.

---

## Summary

Both tools work correctly through Claude Desktop once the underlying
relative-path bugs were fixed. The MCP server itself required no changes
after the initial write — every failure traced back to path assumptions in
code that predates this exercise (Day 4, Day 8, Day 11), which had simply
never been exercised from a working directory other than the project root
until now. Worth keeping in mind for any future integration (a second MCP
client, a scheduled task, a different deployment target) that might also
launch this project's code from an unexpected working directory.
