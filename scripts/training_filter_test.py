"""Live test: 'Trainee/Junior + training' searches must return REAL jobs
only — paid course ads (Netcom etc.) excluded and counted."""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

QUERIES = ["Trainee Data Analyst", "Junior Data Analyst"]


async def call(session, name, args=None):
    result = await session.call_tool(name, args or {})
    texts = [b.text for b in result.content if getattr(b, "type", "") == "text"]
    try:
        return json.loads(texts[0]) if texts else {}
    except (json.JSONDecodeError, IndexError):
        return {"raw": texts[0] if texts else None}


async def main() -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "work_researcher", "serve", "--transport", "stdio"])
    fails = 0
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            for q in QUERIES:
                d = await call(s, "search_jobs", {"query": q,
                                                  "limit_per_source": 25})
                results = d.get("results") or []
                skipped = d.get("training_offers_skipped", 0)
                leaked = [r for r in results
                          if any(w in (r.get("company") or "").lower()
                                 for w in ("netcom", "online learning",
                                           "e-careers", "learning people",
                                           "career switch", "firebrand"))
                          or "apprentice" in (r.get("title") or "").lower()
                          and not r.get("salary_raw")]
                print(f"\n=== {q} ===")
                print(f"shown: {len(results)} | training_offers_skipped: "
                      f"{skipped} | leaked course ads: {len(leaked)}")
                for r in results[:8]:
                    print(f"  {r['title'][:42]:42} | "
                          f"{(r['company'] or '')[:24]:24} | "
                          f"{(r.get('salary_raw') or 'no salary')[:26]}")
                if leaked:
                    fails += 1
                    print("  LEAKED:", [(r["title"], r["company"])
                                        for r in leaked])
            # include_training escape hatch works
            d = await call(s, "search_jobs", {"query": QUERIES[0],
                                              "limit_per_source": 25,
                                              "include_training": True})
            with_t = d.get("results") or []
            print(f"\ninclude_training=true → shown: {len(with_t)} "
                  f"(skipped: {d.get('training_offers_skipped', 0)})")
            has_course = any("netcom" in (r.get("company") or "").lower()
                             for r in with_t)
            print("course ads visible when explicitly requested:", has_course)
    print("\nVERDICT:", "PASS" if fails == 0 else f"FAIL ({fails})")
    return 1 if fails else 0


asyncio.run(main())
