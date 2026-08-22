from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def call(session, name, args=None):
    result = await session.call_tool(name, args or {})
    texts = [b.text for b in result.content if getattr(b, "type", "") == "text"]
    try:
        return json.loads(texts[0]) if texts else {}
    except (json.JSONDecodeError, IndexError):
        return {"raw": texts[0] if texts else None}


async def main():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "work_researcher", "serve", "--transport", "stdio"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            d = await call(s, "browser_open",
                           {"url": "https://uk.indeed.com/account/signin"})
            await call(s, "browser_wait", {"seconds": 3})
            d = await call(s, "browser_snapshot", {"text_chars": 1200})
            print("url:", d.get("url"))
            print("text:", (d.get("text") or "")[:400])
            for e in d.get("elements") or []:
                name = (e.get("name") or "")
                if name and any(w in name.lower() for w in
                                ("continue", "google", "7255", "email", "next",
                                 "create", "sign")):
                    print("  candidate:", e["n"], e["tag"], repr(name[:70]))
            await call(s, "browser_screenshot", {"name": "indeed-signin"})
            await call(s, "browser_close")


asyncio.run(main())
