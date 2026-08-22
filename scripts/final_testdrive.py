"""FINAL TEST DRIVE — full user-workflow verification over real MCP stdio:

get_status → sync_cvs (drive+local) → list_cvs → blocklist → search profile
data_analytics (paging) → search profile field_geologist (earthworks path) →
get_job → check_applied → start_application (guard) → list_applications.
Browser is exercised by a separate script."""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = [sys.executable, "-m", "work_researcher", "serve", "--transport", "stdio"]
PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


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
            tools = sorted(t.name for t in (await session.list_tools()).tools)
            check("tool count = 26", len(tools) == 26, f"{len(tools)}")

            st = await call(session, "get_status")
            check("status: drive configured",
                  st.get("drive", {}).get("configured") is True)
            check("status: adzuna credentials",
                  st["providers"]["adzuna"]["credentials"] is True)
            check("status: home = Blackpool",
                  st.get("home", {}).get("location") == "Blackpool")
            check("status: applicant configured",
                  st.get("applicant_configured") is True)

            sync = await call(session, "sync_cvs", {"source": "both"})
            d = sync.get("drive", {})
            idx = sync.get("index", {})
            check("sync_cvs: drive ok", d.get("ok") is True,
                  f"{d.get('drive_files')} files, skipped={d.get('skipped')}")
            check("sync_cvs: 9 CVs indexed", idx.get("files_found") == 9,
                  f"found={idx.get('files_found')}")

            cvs = await call(session, "list_cvs")
            check("list_cvs: 9 entries with tags",
                  len(cvs.get("cvs", [])) == 9
                  and all(c.get("tags") is not None for c in cvs["cvs"]))

            bl = await call(session, "manage_blocklist", {"action": "list"})
            values = [b["value"] for b in bl.get("blocklist", [])]
            check("blocklist contains Penguin Recruitment",
                  "Penguin Recruitment" in values)

            # profile search 1
            s1 = await call(session, "search_jobs",
                            {"profile": "data_analytics", "limit_per_source": 15})
            reps = {r["provider"]: r for r in s1.get("provider_reports", [])}
            ok_providers = [p for p, r in reps.items() if r["ok"] and r["jobs"] > 0]
            check("search data_analytics: results", s1.get("total", 0) > 10,
                  f"total={s1.get('total')}")
            check("search: totaljobs+reed+adzuna all delivered",
                  {"totaljobs", "reed", "adzuna"} <= set(ok_providers),
                  f"ok={ok_providers}")
            check("search: earthworks skipped for non-geo query",
                  reps.get("earthworks", {}).get("error", "").startswith("skipped"))
            locs = [r for r in s1.get("results", []) if r.get("location_status")]
            check("search: location intelligence present", len(locs) >= 3,
                  f"{len(locs)}/15 rows with location_status")
            # paging
            if s1.get("next_offset") is not None:
                p2 = await call(session, "search_jobs",
                                {"search_id": s1["search_id"],
                                 "offset": s1["next_offset"]})
                check("paging via search_id works",
                      p2.get("showing", "").startswith("16-"),
                      p2.get("showing", "?"))

            # profile search 2 — geologist (earthworks path + blocklist skip)
            s2 = await call(session, "search_jobs",
                            {"profile": "field_geologist", "limit_per_source": 15})
            reps2 = {r["provider"]: r for r in s2.get("provider_reports", [])}
            check("search field_geologist: results", s2.get("total", 0) > 5,
                  f"total={s2.get('total')}")
            ew = reps2.get("earthworks", {})
            check("earthworks ran (ok, with jobs or clean skip)",
                  ew.get("ok") is True, f"jobs={ew.get('jobs')} err={ew.get('error')}")
            check("blocklist skipped Penguin jobs",
                  s2.get("blocked_skipped", 0) > 0,
                  f"skipped={s2.get('blocked_skipped')}")

            # get_job + recommendation path
            rows = [r for r in s2.get("results", []) if r.get("url")]
            job_id = rows[0]["job_id"]
            gj = await call(session, "get_job", {"job_ids": [job_id]})
            if "jobs" in gj:
                gj = gj["jobs"][0]
            check("get_job: full record",
                  bool(gj.get("title")) and bool(gj.get("apply_method"))
                  and "site_playbook" in gj)
            rec = await call(session, "list_cvs", {"job_id": job_id})
            check("list_cvs(job_id): recommendations",
                  len(rec.get("recommendations_for_job") or []) >= 2)

            # application memory guard on a fresh job
            fresh = [r for r in rows if not r.get("already_applied")]
            target = fresh[0] if fresh else rows[0]
            p1 = await call(session, "start_application",
                            {"job_id": target["job_id"]})
            already = p1.get("already_exists")
            if not already:
                check("start_application: plan complete",
                      bool(p1["plan"]["apply_url"]) and p1["plan"]["cv"] is not None
                      and bool(p1["plan"].get("playbook")))
            p2 = await call(session, "start_application",
                            {"job_id": target["job_id"]})
            check("anti-double-apply guard", p2.get("already_exists") is True)
            ca = await call(session, "check_applied",
                            {"url": target.get("url")})
            check("check_applied finds the record", len(ca.get("matches", [])) >= 1)
            # leave the test application as withdrawn (not submitted!)
            app_id = p2.get("application_id")
            await call(session, "record_application", {
                "application_id": app_id, "status": "withdrawn",
                "notes": "final test drive — never submitted"})
            apps = await call(session, "list_applications", {"limit": 3})
            check("list_applications works",
                  isinstance(apps.get("applications"), list))

    print("\n================ FINAL TEST DRIVE (MCP core) ================")
    print(f"PASS: {len(PASS)}  FAIL: {len(FAIL)}")
    if FAIL:
        print("FAILED:", FAIL)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
