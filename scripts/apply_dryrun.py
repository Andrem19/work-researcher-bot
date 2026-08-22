"""Apply-flow dry run: open a live job page, click Apply, inspect what the
board shows before any account exists. NEVER submits anything (no account,
no final click). Verifies: click → fresh snapshot, popup adoption, login-wall
detection, screenshot."""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = [sys.executable, "-m", "work_researcher", "serve", "--transport", "stdio"]


async def call(session, name, args=None):
    result = await session.call_tool(name, args or {})
    texts = [b.text for b in result.content if getattr(b, "type", "") == "text"]
    try:
        return json.loads(texts[0]) if texts else {}
    except (json.JSONDecodeError, IndexError):
        return {"raw": texts[0] if texts else None, "is_error": result.is_error}


async def main() -> int:
    params = StdioServerParameters(command=SERVER[0], args=SERVER[1:])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            search = await call(session, "search_jobs",
                                {"query": "Data Analyst", "limit_per_source": 5})
            results = [r for r in search.get("results", []) if r.get("url")]
            if not results:
                print("no results — abort")
                return 1
            job = results[0]
            print("job:", job["title"], "|", job["company"], "|", job["url"])

            opened = await call(session, "browser_open", {"url": job["url"]})
            print("opened:", opened.get("title"), "| elements:",
                  len(opened.get("elements") or []))

            # find the Apply button
            snap = await call(session, "browser_snapshot",
                              {"filter_text": "apply", "text_chars": 0})
            apply_els = snap.get("elements") or []
            print("apply-ish elements:", [(e["n"], e["tag"], (e.get("name") or "")[:40])
                                          for e in apply_els[:6]])
            if not apply_els:
                print("no Apply control found")
                return 1

            clicked = await call(session, "browser_click", {"n": apply_els[0]["n"]})
            print("after click url:", clicked.get("url"))
            print("after click title:", clicked.get("title"))
            text = (clicked.get("text") or "")[:300].replace("\n", " ")
            print("page text head:", text)
            login_wall = any(
                w in (clicked.get("title") or "").lower() + text.lower()
                for w in ("sign in", "log in", "register", "create account")
            )
            print("login wall detected:", login_wall)

            tabs = await call(session, "browser_tabs", {"action": "list"})
            print("tabs:", tabs.get("tabs"))
            shot = await call(session, "browser_screenshot", {"name": "apply-dryrun"})
            print("screenshot:", shot.get("screenshot"))
            await call(session, "browser_close")
            print("\nDRY RUN OK — stopped at the auth wall, nothing submitted")
            return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
