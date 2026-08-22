import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "work_researcher", "serve", "--transport", "stdio"],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            r = await s.call_tool("search_jobs", {
                "query": "Data Analyst", "limit_per_source": 10})
            d = json.loads(r.content[0].text)
            print("blocked_skipped:", d.get("blocked_skipped"),
                  "| duplicates_merged:", d.get("duplicates_merged"))
            for j in d["results"][:6]:
                print(f"{j['title'][:38]:38} | {(j['company'] or '')[:18]:18} | "
                      f"{(j['location_text'] or '')[:28]:28} | "
                      f"{str(j.get('distance_miles')):>4}mi "
                      f"{str(j.get('location_status')):8} | "
                      f"applied={j['already_applied']}")


asyncio.run(main())
