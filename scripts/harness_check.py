"""Harness connectivity check.

ZCode: spawns the EXACT command from ~/.zcode/cli/config.json and performs an
MCP initialize + tools/list handshake.
OpenCode: validates ~/.config/opencode/opencode.jsonc (comment-aware) and
spawns its command array the same way.
dsh: reads the plugin entry from cordis.patch.yml and spawns its command.
"""

from __future__ import annotations

import asyncio
import io
import json
import re
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

RESULTS: list[tuple[str, bool, str]] = []


def report(name: str, ok: bool, detail: str) -> None:
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} — {detail}")


async def handshake(command: str, args: list[str], label: str) -> None:
    try:
        params = StdioServerParameters(command=command, args=args)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as s:
                await asyncio.wait_for(s.initialize(), timeout=60)
                tools = await asyncio.wait_for(s.list_tools(), timeout=60)
                names = sorted(t.name for t in tools.tools)
                ok = "search_jobs" in names and "browser_login" in names
                report(label, ok, f"initialize OK, {len(names)} tools, "
                                  f"search_jobs/browser_login present")
    except Exception as exc:  # noqa: BLE001
        report(label, False, f"{type(exc).__name__}: {str(exc)[:120]}")


def strip_jsonc(text: str) -> str:
    """Comment-aware JSONC stripper (naive // cuts URLs like https://...)."""
    out = []
    i, n = 0, len(text)
    in_str = False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
                out.append(c)
            elif c == "/" and i + 1 < n and text[i + 1] == "/":
                while i < n and text[i] != "\n":
                    i += 1
                continue
            else:
                out.append(c)
        i += 1
    return "".join(out)


async def main() -> int:
    # --- ZCode ---
    z = json.load(io.open(
        r"C:\Users\andre\.zcode\cli\config.json", encoding="utf-8"))
    entry = z.get("mcp", {}).get("servers", {}).get("work-researcher")
    if not entry:
        report("ZCode config entry", False, "missing")
    else:
        report("ZCode config entry", True,
               f"{entry['command']} {' '.join(entry['args'])}")
        await handshake(entry["command"], entry["args"], "ZCode live handshake")

    # --- OpenCode ---
    raw = io.open(r"C:\Users\andre\.config\opencode\opencode.jsonc",
                  encoding="utf-8").read()
    try:
        oc = json.loads(strip_jsonc(raw))
    except json.JSONDecodeError:
        oc = None
    mcp_entry = (oc or {}).get("mcp", {}).get("work-researcher")
    if not mcp_entry:
        report("OpenCode config entry", False, "missing/invalid")
    else:
        cmd = mcp_entry["command"]
        report("OpenCode config entry", True,
               f"type={mcp_entry.get('type')} enabled={mcp_entry.get('enabled')}")
        await handshake(cmd[0], cmd[1:], "OpenCode live handshake")

    # --- dsh ---
    patch = io.open(
        r"C:\Users\andre\.dsh\profiles\headless\cordis.patch.yml",
        encoding="utf-8").read()
    has_plugin = "mcp-work-researcher" in patch and "dsh-mcp-client" in patch
    report("dsh plugin entry (headless+web)", has_plugin,
           "present in cordis.patch.yml" if has_plugin else "MISSING")
    m = re.search(r'command:\s*"([^"]+)"', patch)
    args_m = re.findall(r"^\s+- (\S+)$", patch.split("args:")[1].split("toolCall")[0], re.M)
    args_clean = [a.strip('"').replace("\\\\", "\\") for a in args_m]
    if m and args_clean:
        await handshake(m.group(1), args_clean, "dsh live handshake")

    print("\n================ HARNESS CHECK ================")
    fails = [r for r in RESULTS if not r[1]]
    print(f"PASS: {len(RESULTS) - len(fails)}  FAIL: {len(fails)}")
    for name, _ok, detail in fails:
        print("  FAILED:", name, "—", detail)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
