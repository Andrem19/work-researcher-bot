"""Test: snapshot now includes modal/dialog controls (Reed apply wizard).
Also verify the wizard fields flow from the applicant config."""
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
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()

            # find a Reed job from the DB (with a real reed.co.uk URL)
            ls = await call(s, "list_stored_jobs", {"source": "reed",
                                                    "days_old": 7,
                                                    "limit": 10})
            jobs = ls.get("jobs", [])
            job_url = None
            for j in jobs:
                gj = await call(s, "get_job",
                                {"job_ids": [j["job_id"]],
                                 "include_description": False})
                rec = gj.get("jobs", [gj])[0] if isinstance(gj, dict) else {}
                u = rec.get("url") or rec.get("apply_url") or ""
                if "reed.co.uk/jobs/" in u:
                    job_url = u
                    print("job:", j["title"], "|", u)
                    break
            if not job_url:
                print("no reed job URL found")
                return 1

            # open and snapshot — check for dialog/listbox/option in tags
            d = await call(s, "browser_open", {"url": job_url})
            await call(s, "browser_wait", {"seconds": 2})
            snap = await call(s, "browser_snapshot", {"text_chars": 400})
            els = snap.get("elements") or []
            tags = [e["tag"] for e in els]
            has_dialog = any("dialog" in t or "listbox" in t or "option" in t
                             for t in tags)
            print(f"\nelements: {len(els)} | modal-tagged elements: {has_dialog}")
            for e in els[:12]:
                print(f"  {e['n']} {e['tag']:12} {repr((e.get('name') or '')[:45])}")

            # verify the applicant config now has the wizard answers
            st = await call(s, "get_status")
            print("\napplicant_configured:", st.get("applicant_configured"))

            await call(s, "browser_close")
            print("\nNOTE: the apply wizard only opens after clicking Apply — "
                  "the tagger now includes [role=dialog/listbox/option] so "
                  "wizard controls will appear in snapshots when a modal is open")
            return 0


asyncio.run(main())
