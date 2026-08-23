from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "work_researcher", "serve", "--transport", "stdio"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            d = await call(s, "browser_open", {
                "url": "https://www.totaljobs.com/job/data-analyst/experis-job107876163"})
            print("title:", d.get("title"), "| elements:", len(d.get("elements") or []))
            await call(s, "browser_wait", {"seconds": 3})
            d = await call(s, "browser_snapshot", {"focus": "buttons", "text_chars": 300})
            els = d.get("elements") or []
            print("buttons:", len(els))
            for e in els[:20]:
                print("  ", e["n"], repr((e.get("name") or "")[:50]))
            await call(s, "browser_screenshot", {"name": "tj-debug"})
            await call(s, "browser_close")


async def call(session, name, args=None):
    result = await session.call_tool(name, args or {})
    texts = [b.text for b in result.content if getattr(b, "type", "") == "text"]
    try:
        return json.loads(texts[0]) if texts else {}
    except (json.JSONDecodeError, IndexError):
        return {"raw": texts[0] if texts else None}


asyncio.run(main())
