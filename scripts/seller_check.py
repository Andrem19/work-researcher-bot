"""Live check: posted_by (agency vs employer) on real search results."""

from __future__ import annotations

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
            for q in ("Data Analyst", "Engineering Geologist"):
                r = await s.call_tool("search_jobs",
                                      {"query": q, "limit_per_source": 15})
                d = json.loads(r.content[0].text)
                rows = d.get("results") or []
                print(f"\n=== {q} ===")
                counts = {}
                for row in rows:
                    pb = row.get("posted_by") or "unknown"
                    counts[pb] = counts.get(pb, 0) + 1
                    print(f"  {row['title'][:36]:36} | "
                          f"{(row['company'] or '')[:22]:22} | {pb:8} | "
                          f"{(row.get('posted_by_reason') or '')[:38]}")
                print("  counts:", counts)


asyncio.run(main())
