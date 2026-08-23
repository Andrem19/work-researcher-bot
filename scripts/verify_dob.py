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
            # find a fresh job to test the applicant block in the plan
            ls = await s.call_tool("list_stored_jobs",
                                   {"query": "trainee", "days_old": 30,
                                    "limit": 3})
            d = json.loads(ls.content[0].text)
            jobs = d.get("jobs", [])
            if jobs:
                plan = await s.call_tool(
                    "start_application", {"job_id": jobs[0]["job_id"]})
                p = json.loads(plan.content[0].text)
                applicant = (p.get("plan") or {}).get("applicant") or {}
                print("applicant block in the apply plan:")
                for k in ("full_name", "phone", "date_of_birth",
                          "nationality", "right_to_work",
                          "right_to_work_docs", "uk_residence_years",
                          "age_group"):
                    print(f"  {k}: {applicant.get(k)!r}")
            r = await s.call_tool("get_status")
            st = json.loads(r.content[0].text)
            print("\napplicant_configured:", st.get("applicant_configured"))


asyncio.run(main())
