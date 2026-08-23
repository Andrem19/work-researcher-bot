"""Test the weak-model-session fixes:
1) duplicate-search guard: run the same query twice → second returns
   note_duplicate with the same search_id
2) list_stored_jobs: query the DB without Bash
3) batch fetch_job_description (2 jobs at once)"""
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
    fails = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()

            # 1) duplicate search guard
            d1 = await call(s, "search_jobs", {"query": "lab technician",
                                               "limit_per_source": 5})
            sid1 = d1.get("search_id")
            d2 = await call(s, "search_jobs", {"query": "lab technician",
                                               "limit_per_source": 5})
            sid2 = d2.get("search_id")
            dup_note = d2.get("note_duplicate")
            print(f"search 1: {sid1} (total {d1.get('total')})")
            print(f"search 2: {sid2} | duplicate note: {bool(dup_note)}")
            if sid1 != sid2 or not dup_note:
                fails.append("dedup guard did not trigger")
            print("  PASS" if sid1 == sid2 and dup_note else "  FAIL")

            # 2) list_stored_jobs
            ls = await call(s, "list_stored_jobs", {"company": "AECOM",
                                                    "days_old": 30})
            jobs = ls.get("jobs", [])
            print(f"\nlist_stored_jobs(company=AECOM): {len(jobs)} jobs")
            for j in jobs[:3]:
                print(f"  {j['title'][:40]} | {j['location']} | "
                      f"req={j.get('requirements_status')}")
            if not isinstance(jobs, list):
                fails.append("list_stored_jobs broken")

            # 3) batch fetch (2 stored jobs with missing descriptions)
            ls2 = await call(s, "list_stored_jobs", {"query": "trainee",
                                                     "days_old": 30,
                                                     "limit": 10})
            no_desc = [j for j in ls2.get("jobs", [])
                       if not j.get("has_description")][:2]
            if no_desc:
                ids = [j["job_id"] for j in no_desc]
                print(f"\nbatch fetch descriptions for: {ids}")
                fd = await call(s, "fetch_job_description", {"job_ids": ids})
                results = fd.get("results", [])
                print(f"  batch results: {len(results)}")
                for r in results:
                    print(f"  {r.get('job_id')}: desc="
                          f"{r.get('description_length')} closed="
                          f"{r.get('vacancy_closed')} req="
                          f"{r.get('requirements_status')}")
                await s.call_tool("browser_close")
                if len(results) != len(ids):
                    fails.append("batch fetch count mismatch")
            else:
                print("\n(all stored trainee jobs already have descriptions — "
                      "skipping batch test)")

    print("\nVERDICT:", "PASS" if not fails else f"FAIL {fails}")
    return 1 if fails else 0


asyncio.run(main())
