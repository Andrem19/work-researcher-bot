"""Live test of all trainee-session fixes:
- agency sellers caught (Noir, Oscar, Zachary Daniels, NowSkills, Back 2 Work)
- NowSkills/Back2Work classified as training providers
- work-mode-aware radius (on_site ≤25, hybrid/field ≤50, remote ∞)
- on_site+mismatch dropped from results"""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

QUERIES = ["Trainee Data Analyst", "Junior Software Developer",
           "Lab Technician", "Operations Coordinator"]
AGENCY_NAMES = {"noir", "oscar", "zachary daniels", "nowskills", "back 2 work",
                "ernest gordon", "halecroft", "njr", "apsley"}
TRAINING_NAMES = {"nowskills", "back 2 work"}


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
    fails = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            for q in QUERIES:
                d = await call(s, "search_jobs",
                                {"query": q, "limit_per_source": 20})
                rows = d.get("results") or []
                loc_skip = d.get("location_skipped", 0)
                train_skip = d.get("training_offers_skipped", 0)
                print(f"\n=== {q} ===")
                print(f"shown: {len(rows)} | training_skipped: {train_skip} "
                      f"| location_skipped: {loc_skip}")

                # check: agency must be TAGGED (posted_by=agency), not removed
                # (the user wants to SEE who posted, not have agencies hidden)
                untagged_agency = []
                leaked_training = []
                for r in rows:
                    pb = (r.get("posted_by") or "").lower()
                    comp = (r.get("company") or "").lower()
                    if any(a in comp for a in AGENCY_NAMES) and pb != "agency":
                        untagged_agency.append((r["title"][:30], comp, pb))
                    if any(t in comp for t in TRAINING_NAMES) \
                            and r.get("posted_by") != "training_offer":
                        leaked_training.append((r["title"][:30], comp))

                if untagged_agency:
                    fails.append(f"{q}: agency not tagged: "
                                  f"{[c for _, c, _ in untagged_agency[:3]]}")
                    print(f"  UNTAGGED AGENCY: {untagged_agency[:3]}")
                if leaked_training:
                    fails.append(f"{q}: training leaked: "
                                  f"{[c for _, c in leaked_training[:3]]}")
                    print(f"  TRAINING LEAKED: {leaked_training[:3]}")

                # check: no on_site+mismatch in results
                for r in rows:
                    wm = r.get("work_mode")
                    ls = r.get("location_status")
                    if ls == "mismatch" and wm != "remote":
                        print(f"  LEAKED MISMATCH: {r['title'][:35]} | "
                              f"{r.get('distance_miles')}mi | {wm}")
                        fails.append(f"{q}: mismatch leaked")

                # show sample with posted_by + work_mode + distance
                for r in rows[:5]:
                    print(f"  {r['title'][:32]:32} | "
                          f"{(r['company'] or '')[:20]:20} | "
                          f"{r.get('posted_by'):8} | "
                          f"{str(r.get('work_mode')):7} | "
                          f"{str(r.get('distance_miles')):>4}mi | "
                          f"{r.get('location_status')}")

    print("\nVERDICT:", "PASS" if not fails else f"FAIL ({len(fails)})")
    return 1 if fails else 0


asyncio.run(main())
