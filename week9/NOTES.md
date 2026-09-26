# Week 9 — MCP: the standard way agents reach tools & data

Track E. Deliverable: bolt a **package-registry** server onto the agent
without touching the agent's code.

---

## 1. The problem MCP solves

In Week 7 the agent's tools were a Python dict I wrote by hand:

```python
TOOLS = {"search_docs": {...}, "lookup_error_code": {...}}
```

Two consequences:

- To add a tool, I edit the agent, re-test it, ship it.
- **Nobody else can reuse my tool.** It only exists inside my agent.

MCP is an industry standard — a common **socket**. A tool behind that socket
can be called by *any* MCP-capable agent, and my agent can call *anyone's*
server.

**The honest framing for a client:** MCP does **not** make the AI smarter.
It is plumbing. It wins on **reuse and swapping**, not on answer quality.
Saying otherwise oversells it.

---

## 2. The three roles

| role | what it is | in this project |
|---|---|---|
| **host** | the app the user talks to — **where the model runs** | `week9/agent_mcp.py` |
| **client** | the connector inside the host that speaks MCP | `week9/mcp_client.py` |
| **server** | offers tools; holds no model | `week9/registry_server.py` |

### Where does the AI run?

**On the host. Never on the server.**

`registry_server.py` contains no model, no API key, and no prompt. It receives
JSON-RPC messages, runs a plain Python function, returns text. It has no idea
which AI is calling it — or whether the caller is an AI at all.

The model's only job is choosing **which** tool to call. Our code does the
calling. Same rule as Week 7.

---

## 3. Transports

| transport | how | when |
|---|---|---|
| **stdio** | host launches the server as a subprocess; they talk over stdin/stdout | a local tool — what we use |
| **HTTP** | server runs elsewhere, serves many hosts | a shared or remote tool |

One consequence of stdio worth knowing: **stdout is the protocol channel.** A
stray `print()` in the server corrupts the stream. Logging goes to stderr.

---

## 4. The raw messages — the whole protocol

`week9/show_handshake.py` deliberately does **not** use the MCP library. It
starts the server as a subprocess and speaks the protocol by hand, printing
every message. After reading it, there is nothing else to MCP.

It is all **JSON-RPC 2.0**:

```
request       {"jsonrpc":"2.0","id":1,"method":"...","params":{...}}
response      {"jsonrpc":"2.0","id":1,"result":{...}}
              {"jsonrpc":"2.0","id":1,"error":{"code":...,"message":...}}
notification  {"jsonrpc":"2.0","method":"..."}      <- no id, no reply
```

An `id` means *"I expect an answer."* No `id` means *"just telling you."*

### The four messages

```
1.  --> initialize                 "I speak MCP version X, here is who I am"
    <-- result                     "so do I, here is what I support"
2.  --> notifications/initialized  (a notification — no reply)
3.  --> tools/list                 "what can you do?"   <-- THIS IS DISCOVERY
    <-- result: [{name, description, inputSchema}, ...]
4.  --> tools/call                 {"name": "...", "arguments": {...}}
    <-- result: content blocks
```

Everything else in MCP is built on those four.

---

## 5. Discovery — the actual deliverable

```python
# week 7
TOOLS = {"search_docs": {...}}     # a dict I wrote

# week 9
tools = await session.list_tools() # ask the server
```

`agent_mcp.py` builds its **own system prompt** from the descriptions that come
back over the wire. It formats what the server said; it adds no knowledge.

Note where the tool description now comes from: the server function's
**docstring**. `fastmcp` turns it into the MCP schema description — which is
exactly what the calling agent reads to choose a tool. Same rule as Week 7:
**the description is the interface**, so each one states *what / USE FOR /
DO NOT USE FOR*.

---

## 6. Proof: a second tool needs zero agent changes

`week9/prove_no_agent_change.py` checks the claim mechanically instead of
asserting it:

1. Hash `agent_mcp.py`.
2. Run discovery against a server with **one** tool → record the list.
3. Run discovery against a server with **two** tools (second added *server
   side only*) → record the list.
4. Hash `agent_mcp.py` again.

```
agent_mcp.py sha256 (before) : ab50b29abc163cff
  server v1: agent discovers ['lookup_package']
  server v2: agent discovers ['lookup_package', 'check_advisories']
agent_mcp.py sha256 (after)  : ab50b29abc163cff

tools gained                         : ['check_advisories']
agent file changed                   : NO
tool names appearing in agent_mcp.py : none
PASS
```

The last check is the strict one: the agent must not even **mention** a tool
name, because a file containing `"lookup_package"` is hard-coding it even if
it never calls it.

**It caught me.** The first version of `agent_mcp.py` named both tools in its
own docstring while claiming it didn't. The test failed, and it was right to.

---

## 6b. An SDK is not the protocol

This week's real bug, found on the machine it was first run on:

```
ModuleNotFoundError: No module named 'mcp.server.fastmcp'.
This is mcp 2.x, where FastMCP was renamed to MCPServer
```

The SDK renamed things between major versions:

| | mcp 1.x | mcp 2.x |
|---|---|---|
| server class | `mcp.server.fastmcp.FastMCP` | `mcp.server.mcpserver.MCPServer` |
| tool schema field | `Tool.inputSchema` | `Tool.input_schema` |
| error flag | `CallToolResult.isError` | `CallToolResult.is_error` |

**The JSON on the wire did not change at all.** Run `show_handshake.py` on
either version and the messages are identical — because that file speaks the
protocol by hand and never imports the SDK.

That is the lesson worth keeping: **the protocol is the contract; the SDK is
just one language's wrapper around it.** Both files now read either spelling,
so they work on 1.x and 2.x — verified on both.

A second lesson from the same bug: the server died *on import*, with the pipe
already open, so the client only saw "connection closed". `stderr` was being
discarded, which made a one-line `ModuleNotFoundError` look like a transport
mystery. **Never throw away a subprocess's stderr.**

## 7. Recoverable errors

A failing tool should return something the **caller can act on**, never crash
the connection:

```
--> tools/call {"name": "no_such_tool"}
<-- {"result": {"content": [{"text": "Unknown tool: no_such_tool"}],
                "isError": true}}
```

Note it comes back as a **result with `isError: true`**, not a transport
error — so the session stays open and the agent can try something else. Same
lesson as Week 7: the error message is part of the interface.

Unknown package → *"'x' is not in the registry. Known packages: …"* The agent
can recover from that. A traceback it cannot.

---

## 8. Safety — before you trust someone else's server

| concern | what we did |
|---|---|
| **least privilege** | the server is **read-only by design**: no writes, no shell, no network, no filesystem. Worst case for a hijacked caller is reading package facts. |
| **trusting a third-party server** | the question reverses: *what can its tools actually do, and who wrote them?* A server you connect runs on someone else's terms — a `delete_file` tool is one `tools/call` away. |
| **auth (remote MCP)** | stdio inherits the local user's trust. Over HTTP you need real auth — a token per client, scoped per tool. |
| **Week 8 link** | an MCP tool result is untrusted input, exactly like a retrieved document. Everything in Week 8's injection section applies to it. |

---

## 9. Run it

```
python week9/show_handshake.py          the raw JSON-RPC, no library  (0 API calls)
python week9/mcp_client.py              discover + call tools         (0 API calls)
python week9/prove_no_agent_change.py   the proof                     (0 API calls)
python week9/agent_mcp.py               the agent using them          (~3 API calls)
```

Three of the four cost **nothing** — the protocol work needs no model at all,
which is itself the point of section 2.

---

## 10. Likely evaluator questions

**Where does the AI run?** On the host. The server holds no model and no key —
it runs plain functions and doesn't know who is calling.

**Does MCP make the AI smarter?** No. It's plumbing. It wins on reuse and
swapping, not answer quality.

**How does the agent know what tools exist?** It asks, with `tools/list`, at
start-up. It builds its prompt from the descriptions it gets back.

**How do you add a tool?** Add it to the server. The agent doesn't change —
proved by hash in `prove_no_agent_change.py`.

**What's on the wire?** JSON-RPC 2.0: `initialize` → `initialized` →
`tools/list` → `tools/call`. That's the whole protocol.

**stdio or HTTP?** stdio for a local tool launched as a subprocess; HTTP for a
remote server serving many hosts.

**What would you check before trusting someone else's server?** What its tools
can actually do — read-only or not — and who wrote them. Plus treat every
result it returns as untrusted input, per Week 8.
