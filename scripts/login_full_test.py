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
            r = await s.call_tool("browser_login",
                                  {"url": "https://www.totaljobs.com"})
            raw = r.content[0].text if r.content else ""
            print("is_error:", r.is_error, "| blocks:", len(r.content))
            try:
                d = json.loads(raw)
                print(json.dumps(d, indent=1, ensure_ascii=False))
            except json.JSONDecodeError:
                print("RAW:", repr(raw[:1500]))
            r = await s.call_tool("browser_close")
            print("closed:", json.loads(r.content[0].text).get("closed"))


asyncio.run(main())
