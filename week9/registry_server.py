"""
WEEK 9 - MY OWN MCP SERVER.  Track E: a package-registry server.

    python week9/registry_server.py        run it as a server (stdio)

WHAT THIS IS
    An MCP server exposing one real capability of a docs app: looking up a
    package in a registry. It speaks the MCP standard, so ANY MCP-capable
    agent - mine, a colleague's, Claude Desktop, an IDE - can call it without
    knowing anything about my code.

    That is the whole point of the week. Before MCP, every tool was wired by
    hand into one agent and reusable by nobody. MCP is a socket.

WHERE THE AI RUNS  (the question the mentor asks)
    NOT here. This process contains no model and no API key. It receives
    JSON-RPC messages, runs a plain Python function, and returns text. The
    AI runs on the HOST side - week9/agent_mcp.py. This server has no idea
    which AI is calling it, or whether the caller is an AI at all.

THE THREE ROLES
    host    the app the user talks to, where the model lives  (agent_mcp.py)
    client  the connector inside the host that speaks MCP     (mcp_client.py)
    server  this file - offers tools, holds no model

TRANSPORT
    stdio: the host launches this file as a subprocess and they exchange
    JSON-RPC over stdin/stdout. Good for a local tool. The alternative is
    HTTP, for a server that runs somewhere else and serves many hosts.

SECURITY NOTE (mentor asks this too)
    This server is READ-ONLY by design - least privilege from week 8. It can
    look things up and nothing else: no writes, no shell, no network, no
    filesystem beyond its own data. If an agent calling it were hijacked by
    a prompt injection, the worst it could do is read package facts.
    Before trusting SOMEONE ELSE's server, the same question applies in
    reverse: what can its tools actually do, and who wrote them?
"""
# ----------------------------------------------------------------------
# VERSION COMPATIBILITY
#
# The SDK renamed its server class between major versions:
#     mcp 1.x   from mcp.server.fastmcp import FastMCP
#     mcp 2.x   from mcp.server.mcpserver import MCPServer
# The decorator and run() API are otherwise the same, so one try/except
# makes this file work on either. Found the hard way: the machine that ran
# this first had 2.x while it was developed against 1.x, and the server died
# on import with the stream already open - which looked like a transport bug
# until stderr was captured.
# ----------------------------------------------------------------------
try:                                              # mcp 2.x
    from mcp.server.mcpserver import MCPServer as _Server
    _SDK = "mcp 2.x (MCPServer)"
except ModuleNotFoundError:                       # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
    _SDK = "mcp 1.x (FastMCP)"

mcp = _Server("phoenixpay-package-registry")

# A small stand-in for a real registry (npm / PyPI). The point of the week is
# the protocol, not the data source - swapping this dict for a real HTTP call
# changes nothing about how the agent discovers or calls the tool.
REGISTRY = {
    "phoenixpay-sdk": {
        "latest": "4.2.1", "license": "MIT", "deprecated": False,
        "min_python": "3.9",
        "note": "Current SDK. Error codes ERR-4xxx are documented in 04_error_codes.md.",
    },
    "phoenixpay-legacy": {
        "latest": "1.9.7", "license": "MIT", "deprecated": True,
        "min_python": "3.6",
        "note": "Deprecated 2025-11-01. Migrate to phoenixpay-sdk 4.x; the "
                "cascade behaviour changed and ERR-4033 is no longer retried "
                "automatically.",
    },
    "phoenixpay-webhooks": {
        "latest": "2.0.3", "license": "Apache-2.0", "deprecated": False,
        "min_python": "3.9",
        "note": "Signature verification helper. Required for webhook replay "
                "protection within the 24 hour window.",
    },
}

ADVISORIES = {
    "phoenixpay-legacy": [
        {"id": "PP-2025-004", "severity": "high",
         "summary": "Webhook signatures are not constant-time compared in "
                    "versions below 1.9.5, allowing a timing attack."},
    ],
    "phoenixpay-webhooks": [
        {"id": "PP-2026-001", "severity": "low",
         "summary": "Replay window was not enforced in 2.0.0 and 2.0.1."},
    ],
}


# ----------------------------------------------------------------------
# TOOL 1
#
# The docstring is not a comment - fastmcp turns it into the tool's
# DESCRIPTION in the MCP schema, which is exactly what a calling agent reads
# to decide whether to use it. Same rule as week 7: description is interface.
# ----------------------------------------------------------------------
@mcp.tool()
def lookup_package(name: str) -> str:
    """Look up a PhoenixPay package in the registry.

    USE FOR: the current version of a package, its license, whether it is
    deprecated, or the minimum Python it needs.
    DO NOT USE FOR: security advisories - use check_advisories for those.
    Input: exactly one package name, e.g. phoenixpay-sdk.
    """
    key = (name or "").strip().lower()
    if key not in REGISTRY:
        known = ", ".join(sorted(REGISTRY))
        return f"'{name}' is not in the registry. Known packages: {known}."
    p = REGISTRY[key]
    state = "DEPRECATED" if p["deprecated"] else "supported"
    return (f"{key} {p['latest']} ({state})\n"
            f"license: {p['license']}\n"
            f"minimum Python: {p['min_python']}\n"
            f"{p['note']}")


# ----------------------------------------------------------------------
# TOOL 2 - added LATER, on purpose.
#
# This is mentor check 2: adding this tool required ZERO changes to
# agent_mcp.py. The agent asks the server what tools exist at start-up, so a
# new @mcp.tool() here simply appears. That is the reuse argument for MCP,
# demonstrated rather than asserted.
# ----------------------------------------------------------------------
@mcp.tool()
def check_advisories(name: str) -> str:
    """Check published security advisories for a PhoenixPay package.

    USE FOR: whether a package has known vulnerabilities, and how severe.
    DO NOT USE FOR: versions, licenses or deprecation - use lookup_package.
    Input: exactly one package name, e.g. phoenixpay-legacy.
    """
    key = (name or "").strip().lower()
    if key not in REGISTRY:
        return f"'{name}' is not in the registry, so no advisories are known."
    items = ADVISORIES.get(key, [])
    if not items:
        return f"{key}: no published advisories."
    return f"{key}: {len(items)} advisory(ies)\n" + "\n".join(
        f"  [{a['id']}] {a['severity'].upper()} - {a['summary']}" for a in items)


if __name__ == "__main__":
    # stdio transport: the host starts this as a subprocess and talks
    # JSON-RPC over stdin/stdout. Nothing is printed to stdout except
    # protocol messages - a stray print() here would corrupt the stream.
    mcp.run(transport="stdio")
