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
            r = await s.call_tool("browser_open", {
                "url": "https://www.totaljobs.com/en-GB/candidate/login"})
            d = json.loads(r.content[0].text)
            print("http:", d.get("http_status"), "| url:", d.get("url"))
            await s.call_tool("browser_wait", {"seconds": 3})
            r = await s.call_tool("browser_snapshot", {"text_chars": 300})
            d = json.loads(r.content[0].text)
            els = d.get("elements") or []
            print("elements:", len(els))
            for e in els:
                name = (e.get("name") or "")
                if any(w in name.lower() for w in ("google", "log in", "sign", "email", "password")):
                    print(" ", e["n"], e["tag"], repr(name[:60]))
            await s.call_tool("browser_close")


asyncio.run(main())
