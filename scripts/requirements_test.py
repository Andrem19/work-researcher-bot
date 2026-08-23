"""Test requirements matching: search for trainee jobs, check that
AAT-requiring jobs are flagged/dropped, and verify descriptions."""
import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, "src")
from work_researcher.requirements import extract_requirements, match_requirements  # noqa


def test_unit():
    """Unit test: AAT Level 2 requirement vs a CV without it."""
    desc = """Trainee Accounts Assistant
Essential:
- AAT Level 2 qualification or equivalent
- GCSE Maths and English (grade 4/C or above)
- 2 years of experience in an office environment
- Proficiency in Microsoft Excel
Desirable:
- AAT Level 3
- Experience with Sage"""
    cv_no_aat = """ANDREW REMNIOW
BSc Geology
Skills: Python, SQL, Excel, data analysis, fieldwork,
site investigation, borehole supervision, full UK driving licence."""

    reqs = extract_requirements(desc)
    print("extracted hard requirements:")
    for r in reqs["hard"]:
        print(f"  [{r['type']:14}] {r['value']}")
    print("desirable:", [r["value"] for r in reqs["desirable"]])
    print("experience_years:", reqs["experience_years"])

    match = match_requirements(reqs, cv_no_aat)
    print("\nmatch:", json.dumps(match, indent=1))

    # verify AAT is unmet
    aat_unmet = any("AAT" in u["value"] for u in match["unmet"])
    print(f"\nAAT Level 2 unmet: {aat_unmet} (expected True)")
    return aat_unmet and match["status"] == "gap"


async def test_live():
    """Live test: search trainee jobs, check requirements fields."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "work_researcher", "serve", "--transport", "stdio"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            r = await s.call_tool("search_jobs", {
                "query": "Trainee Accounts", "limit_per_source": 15})
            d = json.loads(r.content[0].text)
            print(f"\n=== LIVE SEARCH: Trainee Accounts ===")
            print(f"total: {d.get('total')} | req_skipped: {d.get('req_skipped', 'N/A')}")
            for row in d.get("results", [])[:8]:
                print(f"  {row['title'][:35]:35} | "
                      f"req={str(row.get('requirements_status')):8} | "
                      f"unmet={row.get('requirements_unmet') or []} | "
                      f"desc={'yes' if row.get('description_excerpt') else 'null'}")


async def main():
    ok = test_unit()
    await test_live()
    print("\nUNIT VERDICT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


asyncio.run(main())
