"""
WEEK 9 - THE RAW JSON-RPC HANDSHAKE, printed once.

    python week9/show_handshake.py

WHY THIS FILE EXISTS
    The brief says: look at the raw messages once, so MCP stops being a
    mystery. So this file does NOT use the mcp library at all. It starts the
    server as a subprocess and speaks the protocol by hand - writing JSON
    lines to its stdin and reading JSON lines from its stdout.

    After reading this you know the entire protocol. There is nothing else.

THE SHAPE OF EVERY MESSAGE  (JSON-RPC 2.0)
    request       {"jsonrpc":"2.0","id":1,"method":"...","params":{...}}
    response      {"jsonrpc":"2.0","id":1,"result":{...}}
                  {"jsonrpc":"2.0","id":1,"error":{"code":...,"message":...}}
    notification  {"jsonrpc":"2.0","method":"..."}      <- no id, no reply

    An `id` means "I expect an answer". No `id` means "just telling you".

WHY THE PIPES ARE BINARY  (this cost a real bug on Windows)
    Opening the pipes in TEXT mode makes Python translate "\\n" into "\\r\\n"
    on Windows. MCP frames one JSON object per line, so the extra carriage
    return corrupts the framing and the server closes the stream - which
    looks, confusingly, like the server crashed for no reason.

    Binary mode does no translation, so we encode and decode UTF-8 ourselves
    and the bytes on the wire are identical on every platform.

    Second lesson from the same bug: stderr was being thrown away, so the
    server's own error message was invisible. It is captured now and printed
    if the server dies.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "registry_server.py")


def show(direction: str, msg: dict, note: str = "") -> None:
    arrow = "-->" if direction == "out" else "<--"
    who = "HOST -> SERVER" if direction == "out" else "SERVER -> HOST"
    print(f"\n  {arrow} {who}   {note}")
    text = json.dumps(msg, indent=2)
    if len(text) > 1400:
        text = text[:1400] + "\n  ... (truncated)"
    for line in text.splitlines():
        print("      " + line)


def main() -> None:
    print("=" * 78)
    print("MCP - THE RAW MESSAGES")
    print("=" * 78)
    print("  transport: stdio. The host starts the server as a subprocess and")
    print("  they exchange one JSON object per line over stdin/stdout.")
    print("  (binary pipes, so no newline translation on any platform)")

    # stderr goes to a real file so we can show it if the server dies.
    err_fd, err_path = tempfile.mkstemp(suffix="_mcp_stderr.log")
    err_file = os.fdopen(err_fd, "w+b")

    proc = subprocess.Popen(
        [sys.executable, "-u", SERVER],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err_file,
        bufsize=0,                       # binary, unbuffered - no translation
    )

    def server_error() -> str:
        err_file.flush()
        err_file.seek(0)
        return err_file.read().decode("utf-8", "replace").strip()

    def dead() -> bool:
        return proc.poll() is not None

    def send(msg: dict, note: str = "") -> bool:
        show("out", msg, note)
        if dead():
            print("\n  !! the server has already exited - not sending")
            return False
        try:
            proc.stdin.write((json.dumps(msg) + "\n").encode("utf-8"))
            proc.stdin.flush()
            return True
        except OSError as e:
            print(f"\n  !! could not write to the server: {e}")
            return False

    def recv(note: str = "") -> dict:
        try:
            line = proc.stdout.readline()
        except OSError as e:
            print(f"\n  !! could not read from the server: {e}")
            return {}
        if not line:
            print("\n  !! the server closed the stream without replying.")
            err = server_error()
            if err:
                print("  --- the server's own error output ---")
                for l in err.splitlines()[-20:]:
                    print("      " + l)
            else:
                print("  (it printed nothing to stderr)")
            return {}
        msg = json.loads(line.decode("utf-8"))
        show("in", msg, note)
        return msg

    ok = True
    try:
        # ---- 1. initialize -------------------------------------------
        ok = send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                   "params": {"protocolVersion": "2024-11-05",
                              "capabilities": {},
                              "clientInfo": {"name": "week9-by-hand",
                                             "version": "1.0"}}},
                  "step 1: who I am, which protocol version I speak")
        if ok and not recv("the server answers with its info and capabilities"):
            ok = False

        # ---- 2. initialized notification -----------------------------
        if ok:
            ok = send({"jsonrpc": "2.0", "method": "notifications/initialized"},
                      "step 2: a NOTIFICATION - no id, so no reply is expected")

        # ---- 3. tools/list -------------------------------------------
        listed = {}
        if ok:
            ok = send({"jsonrpc": "2.0", "id": 2, "method": "tools/list",
                       "params": {}},
                      "step 3: THIS is tool discovery - 'what can you do?'")
        if ok:
            listed = recv("every tool, with the description an agent reads")
            ok = bool(listed)

        if ok:
            names = [t["name"] for t in listed.get("result", {}).get("tools", [])]
            print(f"\n  >>> discovered: {names}")
            print("  >>> the agent did not know these names until this moment.")

        # ---- 4. tools/call -------------------------------------------
        if ok:
            ok = send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                       "params": {"name": "lookup_package",
                                  "arguments": {"name": "phoenixpay-sdk"}}},
                      "step 4: call one by name, arguments matching its schema")
        if ok:
            ok = bool(recv("the result comes back as content blocks"))

        # ---- 5. a recoverable error ----------------------------------
        if ok:
            ok = send({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                       "params": {"name": "no_such_tool", "arguments": {}}},
                      "step 5: ask for a tool that does not exist")
        if ok:
            ok = bool(recv("an error - the connection stays open and usable"))

    finally:
        for closer in (lambda: proc.stdin.close(), proc.terminate):
            try:
                closer()
            except Exception:
                pass
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        try:
            err_file.close()
            os.remove(err_path)
        except Exception:
            pass

    if not ok:
        print("\n" + "=" * 78)
        print("The exchange did not complete. Nothing above is wrong with MCP")
        print("itself - see the server error printed above for the cause.")
        print("=" * 78)
        raise SystemExit(1)

    print("\n" + "=" * 78)
    print("""THAT IS THE WHOLE PROTOCOL
  initialize -> initialized -> tools/list -> tools/call.
  Everything else in MCP is built on those four messages.

  Where does the AI run? Nowhere in the above. Not one of these messages
  contains a model, a prompt or an API key. The server ran a plain Python
  function. The model lives on the HOST side and only decides WHICH tool to
  call - the calling itself is ordinary software talking to ordinary
  software.""")


if __name__ == "__main__":
    main()
