"""Test fetch_job_description on a real Totaljobs job."""
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
            # search for a job first
            r = await s.call_tool("search_jobs", {
                "query": "Trainee Accounts", "limit_per_source": 10,
                "sources": ["totaljobs"]})
            d = json.loads(r.content[0].text)
            rows = d.get("results") or []
            if not rows:
                print("no results")
                return 1
            job = rows[0]
            print(f"job: {job['title']} | {job['job_id']}")
            print(f"desc before: {job.get('description_excerpt') or 'null'}")

            # fetch the full description
            r = await s.call_tool("fetch_job_description",
                                  {"job_id": job["job_id"]})
            d2 = json.loads(r.content[0].text)
            print(f"\nfetch result:")
            print(f"  desc length: {d2.get('description_length')}")
            print(f"  preview: {str(d2.get('description_preview'))[:300]}")
            print(f"  req status: {d2.get('requirements_status')}")
            print(f"  req unmet: {d2.get('requirements_unmet')}")
            print(f"  req hard: {d2.get('requirements_hard')}")
            await s.call_tool("browser_close")
            return 0


asyncio.run(main())
