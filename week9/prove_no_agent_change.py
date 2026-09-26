"""
WEEK 9 - PROOF: a second tool needs ZERO changes to the agent.

    python week9/prove_no_agent_change.py        (no API calls)

This is mentor check 2, demonstrated rather than claimed.

HOW THE PROOF WORKS
    1. Hash week9/agent_mcp.py.
    2. Start a server exposing ONE tool. Ask the agent's discovery code what
       tools exist. Record the answer.
    3. Start a server exposing TWO tools - the second added only on the
       SERVER side. Ask again. Record the answer.
    4. Hash week9/agent_mcp.py again.

    The tool list changes. The agent's bytes do not. That is the argument
    for MCP, checked rather than asserted.

    It also checks the harder claim: the agent file must not CONTAIN either
    tool name anywhere - because a file that mentions "lookup_package" is
    hard-coding it even if it never calls it.
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.join(HERE, "agent_mcp.py")
SERVER = os.path.join(HERE, "registry_server.py")


def sha(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]


def discover_from(server_path: str) -> list:
    """Run the agent's own discovery code against an arbitrary server file."""
    code = (
        "import sys, json, asyncio\n"
        f"sys.path.insert(0, {os.path.dirname(HERE)!r})\n"
        "from week9 import mcp_client\n"
        f"mcp_client.SERVER = {server_path!r}\n"
        "print('TOOLS:' + json.dumps([t['name'] for t in mcp_client.discover_sync()]))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, timeout=90)
    for line in out.stdout.splitlines():
        if line.startswith("TOOLS:"):
            return json.loads(line[len("TOOLS:"):])
    raise SystemExit(f"discovery failed:\n{out.stdout}\n{out.stderr}")


def one_tool_server() -> str:
    """The same server with the second tool removed - an 'earlier version'."""
    src = open(SERVER, encoding="utf-8").read()
    marker = "@mcp.tool()\ndef check_advisories"
    cut = src.index(marker)
    trimmed = src[:cut] + '\n\nif __name__ == "__main__":\n    mcp.run(transport="stdio")\n'
    fd, path = tempfile.mkstemp(suffix="_server_v1.py", dir=HERE)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(trimmed)
    return path


def main() -> None:
    print("=" * 78)
    print("PROOF - ADDING A TOOL DOES NOT TOUCH THE AGENT")
    print("=" * 78)

    before_hash = sha(AGENT)
    print(f"\n  agent_mcp.py sha256 (before) : {before_hash}")

    v1 = one_tool_server()
    try:
        print("\n  --- server v1: one tool ---")
        t1 = discover_from(v1)
        print(f"      agent discovers: {t1}")

        print("\n  --- server v2: a second tool added, SERVER SIDE ONLY ---")
        t2 = discover_from(SERVER)
        print(f"      agent discovers: {t2}")
    finally:
        os.remove(v1)

    after_hash = sha(AGENT)
    print(f"\n  agent_mcp.py sha256 (after)  : {after_hash}")

    added = [t for t in t2 if t not in t1]

    print("\n" + "-" * 78)
    print(f"  tools gained            : {added}")
    print(f"  agent file changed      : {'YES' if before_hash != after_hash else 'NO'}")

    # The stronger check: the agent must not even MENTION a tool name.
    agent_src = open(AGENT, encoding="utf-8").read()
    mentioned = [t for t in t2 if t in agent_src]
    print(f"  tool names appearing in agent_mcp.py : "
          f"{mentioned if mentioned else 'none'}")

    ok = (before_hash == after_hash) and added and not mentioned
    print("\n" + "=" * 78)
    if ok:
        print(f"  PASS - the agent gained {added[0]} without a single byte")
        print("         changing in agent_mcp.py, and does not name any tool.")
    else:
        print("  FAIL - see above")
    print("=" * 78)
    print("""
  WHY THIS IS THE WHOLE POINT
    In week 7 the tools were a dict inside the agent. Adding one meant
    editing the agent, re-testing it, and shipping it. Nobody else could
    reuse the tool.

    Here the tool lives behind a standard socket. The agent asks what is
    there. A colleague can point the same agent at THEIR server and it
    works, and my registry server can be called by THEIR agent.

    Honest framing for a client: MCP does not make the AI smarter. It is
    plumbing. It wins on reuse and swapping, not on answer quality.""")


if __name__ == "__main__":
    main()
