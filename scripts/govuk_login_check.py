"""Verify browser_login correctly detects the active GOV.UK One Login session."""
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
            v = await call(s, "browser_login",
                           {"url": "https://www.jobs.service.gov.uk/jobs"})
            print("browser_login verdict:", json.dumps(
                {k: v.get(k) for k in
                 ("logged_in", "needs_user", "note", "url")},
                indent=1, ensure_ascii=False))
            await call(s, "browser_close")


asyncio.run(main())
