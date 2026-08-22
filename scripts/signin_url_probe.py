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
    urls = [
        "https://www.reed.co.uk/account/signin",
        "https://uk.indeed.com/account/signin",
        "https://www.totaljobs.com/account/signin",
    ]
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            for url in urls:
                d = await call(s, "browser_open", {"url": url})
                await call(s, "browser_wait", {"seconds": 3})
                d = await call(s, "browser_snapshot", {"text_chars": 1500})
                els = d.get("elements") or []
                pw = [e for e in els if e.get("type") == "password"]
                google = [e for e in els if "google" in (e.get("name") or "").lower()]
                print(f"{url}")
                print(f"  final url: {d.get('url')}")
                print(f"  password inputs: {len(pw)} | google controls: "
                      f"{[(e['n'], e.get('name')) for e in google[:3]]}")
                print(f"  text head: {(d.get('text') or '')[:100]}")
                print()
            await call(s, "browser_close")


asyncio.run(main())
