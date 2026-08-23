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
            v = await call(s, "browser_login",
                           {"url": "https://www.cv-library.co.uk"})
            print("CV-Library verdict:", json.dumps(
                {k: v.get(k) for k in ("logged_in", "needs_user", "note", "url")},
                indent=1, ensure_ascii=False))
            # sanity: session survives a browser restart (profile persistence)
            await call(s, "browser_close")
            v2 = await call(s, "browser_login",
                            {"url": "https://www.cv-library.co.uk"})
            print("after restart:", json.dumps(
                {k: v2.get(k) for k in ("logged_in", "needs_user", "note")},
                ensure_ascii=False))
            await call(s, "browser_close")


asyncio.run(main())
