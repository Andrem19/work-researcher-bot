"""Direct check: open a Reed job page, verify snapshot elements render."""
import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def call(s, name, args=None):
    r = await s.call_tool(name, args or {})
    t = [b.text for b in r.content if getattr(b, "type", "") == "text"]
    try:
        return json.loads(t[0]) if t else {}
    except (json.JSONDecodeError, IndexError):
        return {"raw": t[0] if t else None}


async def main():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "work_researcher", "serve", "--transport", "stdio"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            d = await call(s, "browser_open",
                           {"url": "https://www.reed.co.uk/jobs/entry-level-grad-scheme/57262727"})
            print("title:", d.get("title"), "| status:", d.get("http_status"))
            els = d.get("elements") or []
            print("elements from open:", len(els))
            await call(s, "browser_wait", {"seconds": 3})
            snap = await call(s, "browser_snapshot", {"text_chars": 300})
            els = snap.get("elements") or []
            print("elements after wait:", len(els))
            for e in els[:10]:
                print(f"  {e['n']} {e['tag']:10} {repr((e.get('name') or '')[:40])}")
            await call(s, "browser_close")


asyncio.run(main())
