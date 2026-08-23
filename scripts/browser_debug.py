"""Direct browser debug: what does browser_open actually return?"""
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
            for url in ("https://example.com",
                        "https://www.reed.co.uk/jobs/entry-level-grad-scheme/57262727"):
                r = await s.call_tool("browser_open", {"url": url})
                raw = r.content[0].text if r.content else ""
                try:
                    d = json.loads(raw)
                except json.JSONDecodeError:
                    d = {"RAW": raw[:500]}
                print(url)
                print("  error:", d.get("error"))
                print("  title:", d.get("title"), "| url:", d.get("url"))
                print("  elements:", len(d.get("elements") or []))
            await s.call_tool("browser_close")


asyncio.run(main())
