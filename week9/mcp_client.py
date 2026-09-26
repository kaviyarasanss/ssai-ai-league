"""
WEEK 9 - THE MCP CLIENT: discover tools instead of hard-coding them.

    python week9/mcp_client.py            connect, list tools, call one

THE ONE IDEA
    In week 7 the agent's tools were a Python dict I wrote by hand. To add a
    tool I edited the agent. Here the agent asks the server "what can you
    do?" and gets back a list with names, descriptions and input schemas.
    Adding a tool means adding it to the SERVER. The agent never changes.

    Hard-coded:  TOOLS = {"search_docs": {...}, "lookup_error_code": {...}}
    Discovered:  tools = await session.list_tools()

WHAT HAPPENS ON THE WIRE  (run with --raw to watch it)
    1. host launches the server as a subprocess (stdio transport)
    2. -> initialize            "I speak MCP version X, here is who I am"
       <- initialize result     "so do I, here is what I support"
    3. -> notifications/initialized
    4. -> tools/list            "what can you do?"
       <- result: [ {name, description, inputSchema}, ... ]
    5. -> tools/call            {"name": "...", "arguments": {...}}
       <- result: content blocks
    All of it is JSON-RPC 2.0: an id, a method, params, and either a result
    or an error. There is no magic in MCP - this is the whole protocol.

RECOVERABLE ERRORS
    A tool that fails should return an error the CALLER can act on, not crash
    the connection. Week 7's lesson about helpful tool errors is the same
    lesson: the message is part of the interface.
"""
import asyncio
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "registry_server.py")

from mcp import ClientSession, StdioServerParameters      # noqa: E402
from mcp.client.stdio import stdio_client                 # noqa: E402


# ----------------------------------------------------------------------
# VERSION COMPATIBILITY
#
# The SDK renamed two model fields between major versions:
#     mcp 1.x   Tool.inputSchema   CallToolResult.isError
#     mcp 2.x   Tool.input_schema  CallToolResult.is_error
# Reading both keeps this file working on either. Worth knowing generally:
# an SDK is not the protocol. The JSON on the wire did not change at all
# (see show_handshake.py) - only the Python names for it did.
# ----------------------------------------------------------------------
def _schema_of(tool) -> dict:
    return getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None) or {}


def _is_error(result) -> bool:
    v = getattr(result, "is_error", None)
    if v is None:
        v = getattr(result, "isError", None)
    return bool(v)


def server_params() -> StdioServerParameters:
    """How to start the server. This - a command and its arguments - is the
    ENTIRE configuration needed to bolt a tool onto the agent."""
    return StdioServerParameters(command=sys.executable, args=[SERVER], env=None)


async def discover() -> list:
    """Connect and ask the server what tools it has. Returns plain dicts so
    the agent never imports anything MCP-specific."""
    async with stdio_client(server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            return [{"name": t.name,
                     "description": (t.description or "").strip(),
                     "schema": _schema_of(t)} for t in listed.tools]


async def call(name: str, arguments: dict) -> str:
    """Call one discovered tool by name and return its text."""
    async with stdio_client(server_params()) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
            parts = [getattr(b, "text", str(b)) for b in (result.content or [])]
            text = "\n".join(parts).strip()
            if _is_error(result):
                return f"Tool error (recoverable): {text}"
            return text


# ----------------------------------------------------------------------
# A tiny synchronous wrapper, so the rest of the project - which is all
# ordinary blocking code - does not have to become async.
# ----------------------------------------------------------------------
def discover_sync() -> list:
    return asyncio.run(discover())


def call_sync(name: str, arguments: dict) -> str:
    return asyncio.run(call(name, arguments))


def main() -> None:
    print("=" * 78)
    print("MCP TOOL DISCOVERY")
    print("=" * 78)
    print(f"  transport : stdio")
    print(f"  server    : {os.path.basename(SERVER)} (launched as a subprocess)")
    print(f"  the AI    : does NOT run here. This client holds no model.\n")

    tools = discover_sync()
    print(f"  discovered {len(tools)} tool(s) - none of these are hard-coded "
          f"in the agent:\n")
    for t in tools:
        first = t["description"].splitlines()[0] if t["description"] else ""
        props = list((t["schema"] or {}).get("properties", {}))
        print(f"    - {t['name']}({', '.join(props)})")
        print(f"        {first}")

    print("\n" + "-" * 78)
    print("CALLING A DISCOVERED TOOL")
    print("-" * 78)
    for name, args in [("lookup_package", {"name": "phoenixpay-legacy"}),
                       ("check_advisories", {"name": "phoenixpay-legacy"}),
                       ("lookup_package", {"name": "not-a-real-package"})]:
        print(f"\n  -> {name}({args})")
        for line in call_sync(name, args).splitlines():
            print(f"     {line}")
    print("\n  Note the last one: an unknown package returns a helpful message,"
          "\n  not a crash. The connection stays usable - a recoverable error.")


if __name__ == "__main__":
    main()
