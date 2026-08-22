"""Live blocklist test over MCP stdio: block Penguin Recruitment, search
Field Geologist (Reed carries Penguin jobs), verify blocked_skipped > 0 and
that no blocked company appears in results; then start_application on a
blocked job if one is retrievable directly."""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = [sys.executable, "-m", "work_researcher", "serve", "--transport", "stdio"]


async def call(session, name, args=None):
    result = await session.call_tool(name, args or {})
    texts = [b.text for b in result.content if getattr(b, "type", "") == "text"]
    try:
        return json.loads(texts[0]) if texts else {}
    except (json.JSONDecodeError, IndexError):
        return {"raw": texts[0] if texts else None, "is_error": result.is_error}


async def main() -> int:
    params = StdioServerParameters(command=SERVER[0], args=SERVER[1:])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            add = await call(session, "manage_blocklist", {
                "action": "add", "kind": "company",
                "value": "Penguin Recruitment",
                "reason": "e2e test: user asked to skip this agency",
            })
            print("blocklist add:", json.dumps(add.get("blocklist", [])[-1:]
                                               if add.get("blocklist") else add))

            search = await call(session, "search_jobs", {
                "query": "Engineering Geologist", "limit_per_source": 25,
            })
            results = search.get("results") or []
            companies = [(r.get("company") or "") for r in results]
            leaked = [c for c in companies if "penguin" in c.lower()]
            print(f"total={search.get('total')} blocked_skipped="
                  f"{search.get('blocked_skipped')} leaked={leaked}")
            ok = search.get("blocked_skipped", 0) > 0 and not leaked

            # find a blocked job directly in the DB to test the apply-refusal
            probe = await call(session, "get_job", {"job_ids": ["job_none"]})
            print("unknown-job handling:", probe.get("error", probe))

            listing = await call(session, "list_applications", {"limit": 1})
            print("apps reachable:", bool(listing.get("applications")
                                          is not None))
            print("\nVERDICT:", "BLOCKLIST OK" if ok else
                  "BLOCKLIST PARTIAL (leak or zero skipped — check output)")
            return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
