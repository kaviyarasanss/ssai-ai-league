# Week 9 — Results

Three of the four scripts cost **zero API calls** — the protocol work needs no
model at all, which is itself the point.

---

## Mentor check 1 — the agent uses a tool through MCP, discovered not hard-coded

`python week9/agent_mcp.py` (~3 requests)

```
discovered 2 tool(s) over MCP: lookup_package, check_advisories

step 1  ACTION: lookup_package('phoenixpay-legacy')     [over MCP]
        OBSERVE: phoenixpay-legacy 1.9.7 (DEPRECATED) ...
step 2  ACTION: check_advisories('phoenixpay-legacy')   [over MCP]
        OBSERVE: [PP-2025-004] HIGH - Webhook signatures are not constant-time...
step 3  FINAL
stop_reason: completed      3 steps / 3 calls
```

The agent's system prompt is **built at runtime** from the descriptions the
server returned. Nothing in `agent_mcp.py` names a tool.

## Mentor check 2 — a second tool without changing the agent's code

`python week9/prove_no_agent_change.py` (0 requests)

```
agent_mcp.py sha256 (before) : ab50b29abc163cff
  server v1 (one tool) : agent discovers ['lookup_package']
  server v2 (two tools): agent discovers ['lookup_package', 'check_advisories']
agent_mcp.py sha256 (after)  : ab50b29abc163cff

tools gained                         : ['check_advisories']
agent file changed                   : NO
tool names appearing in agent_mcp.py : none
PASS
```

The strict third line matters: a file *containing* `"lookup_package"` is
hard-coding it even if it never calls it.

**This test caught a real violation.** The first `agent_mcp.py` named both
tools in its own docstring while claiming it didn't. The check failed, and it
was right to.

## Mentor check 3 — a server another person's agent could call

`week9/registry_server.py` — a `fastmcp` stdio server exposing two tools:

| tool | purpose |
|---|---|
| `lookup_package(name)` | version, license, deprecation, minimum Python |
| `check_advisories(name)` | published security advisories and severity |

It speaks standard MCP, so any MCP-capable host — my agent, a colleague's,
Claude Desktop, an IDE — can use it. Nothing about it is specific to my code.

`python week9/mcp_client.py` (0 requests) verifies discovery and all three
call paths:

```
discovered 2 tool(s) - none hard-coded in the agent:
   - lookup_package(name)
   - check_advisories(name)

-> lookup_package({'name': 'phoenixpay-legacy'})
   phoenixpay-legacy 1.9.7 (DEPRECATED) ...
-> check_advisories({'name': 'phoenixpay-legacy'})
   [PP-2025-004] HIGH - Webhook signatures are not constant-time compared...
-> lookup_package({'name': 'not-a-real-package'})
   'not-a-real-package' is not in the registry. Known packages: ...
```

The third is a **recoverable error**: a helpful message, connection still
usable, agent free to try something else.

## Mentor check 4 — explain where the AI runs, in plain words

`python week9/show_handshake.py` (0 requests) prints every raw JSON-RPC
message, without using the MCP library at all:

```
--> initialize                  "I speak MCP version X, here is who I am"
<-- result                      server info + capabilities
--> notifications/initialized   a notification: no id, so no reply
--> tools/list                  <-- THIS IS DISCOVERY
<-- result                      [{name, description, inputSchema}, ...]
--> tools/call                  {"name": "...", "arguments": {...}}
<-- result                      content blocks
--> tools/call no_such_tool
<-- result                      {"isError": true, "text": "Unknown tool: ..."}
```

**Where the AI runs:** on the host, never on the server. Not one of those
messages contains a model, a prompt or an API key. The server ran a plain
Python function and has no idea whether the caller is an AI at all. The model
only decides **which** tool to call; the calling is ordinary software talking
to ordinary software.

Note the error shape: `isError: true` inside a **result**, not a transport
failure — so the session stays open.

---

## Verification summary

| check | cost | result |
|---|---|---|
| raw JSON-RPC handshake, no library | 0 | ✔ all 5 messages, real protocol |
| tool discovery over stdio | 0 | ✔ 2 tools with schemas |
| calling a discovered tool | 0 | ✔ both tools return real data |
| recoverable error on unknown package | 0 | ✔ helpful message, session alive |
| recoverable error on unknown tool | 0 | ✔ `isError: true`, session alive |
| second tool, zero agent changes | 0 | ✔ PASS, hash identical, no names |
| agent end-to-end over MCP | ~3 | ✔ completed, 3 steps |

## The bug this week found

First run on the target machine failed: its venv had **mcp 2.x**, the code was
written against **1.x**, and the server died on import — `FastMCP` had been
renamed to `MCPServer`. The client only saw `Connection closed`, because the
subprocess's stderr was being discarded.

Two fixes, both verified on **1.30.0 and 2.2.0**:

| | fix |
|---|---|
| SDK rename | read either spelling: `MCPServer`/`FastMCP`, `input_schema`/`inputSchema`, `is_error`/`isError` |
| invisible cause | capture the server's stderr and print it when the stream closes |

Plus a Windows-only one found in the same run: text-mode pipes translate `\n`
to `\r\n`, corrupting the one-JSON-object-per-line framing. `show_handshake.py`
now uses binary pipes.

**None of this touched the protocol.** The raw JSON is byte-identical on both
SDK versions — which is the point of section 4: the protocol is the contract,
the SDK is one language's wrapper.

## Honest framing

MCP does **not** make the AI smarter. It is plumbing. It wins on **reuse and
swapping**, not on answer quality — and that is what to tell a client.

## Safety

The server is **read-only by design** (Week 8's least privilege): no writes,
no shell, no network, no filesystem. The worst a hijacked caller achieves is
reading package facts.

Reversed, that is the question to ask before trusting *someone else's* server:
what can its tools actually do, and who wrote them? A `delete_file` tool is
one `tools/call` away. And an MCP tool result is untrusted input exactly like
a retrieved document — everything in Week 8's injection section applies to it.
