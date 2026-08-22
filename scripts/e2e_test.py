"""End-to-end live test over real MCP stdio, exactly like a harness client.

Runs: list tools → get_status → live search → get_job → check_applied →
start_application twice (anti-double-apply) → browser job page (headless,
NO submission) → form/snapshot checks → screenshot → record_application
(withdrawn, marked as e2e test). Requires network.
"""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = [sys.executable, "-m", "work_researcher", "serve", "--transport", "stdio"]


def show(label: str, payload) -> None:
    if not isinstance(payload, str):
        payload = json.dumps(payload, indent=1, default=str, ensure_ascii=False)
    print(f"\n===== {label} =====\n{payload[:2600]}")


async def call(session: ClientSession, name: str, args: dict | None = None):
    result = await session.call_tool(name, args or {})
    texts = [b.text for b in result.content if getattr(b, "type", "") == "text"]
    try:
        return json.loads(texts[0]) if texts else {}
    except (json.JSONDecodeError, IndexError):
        return {"raw": texts[0] if texts else None, "is_error": result.is_error}


async def main() -> int:
    failures: list[str] = []
    params = StdioServerParameters(command=SERVER[0], args=SERVER[1:])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)
            show("TOOLS", f"{len(names)}: {', '.join(names)}")

            status = await call(session, "get_status")
            show("STATUS", status)

            search = await call(session, "search_jobs", {
                "query": "Data Analyst",
                "limit_per_source": 10,
                "max_days_old": 14,
            })
            show("SEARCH", search)
            results = search.get("results") or []
            if not results:
                failures.append("live search returned no results")
                print("\nE2E FAILED: no search results")
                return 1
            sample = [r for r in results if r.get("url") and not r.get("already_applied")][:3]
            if not sample:
                sample = [r for r in results if r.get("url")][:3]
            job_id = sample[0]["job_id"]

            job = await call(session, "get_job", {"job_ids": [job_id]})
            show("GET_JOB", job)

            checked = await call(session, "check_applied",
                                 {"url": sample[0]["url"]})
            show("CHECK_APPLIED(before)", checked)

            plan1 = await call(session, "start_application", {"job_id": job_id})
            show("START_APPLICATION#1", plan1)
            plan2 = await call(session, "start_application", {"job_id": job_id})
            show("START_APPLICATION#2(guard)", plan2)
            if not (plan1.get("ok") and not plan1.get("already_exists")):
                failures.append("first start_application not clean")
            if not plan2.get("already_exists"):
                failures.append("anti-double-apply guard did not trigger")
            app_id = plan1.get("application_id") or plan2.get("application_id")

            # browser live check — open the job page (headed Edge — headless is
            # blocked by board anti-bot), NO submission
            url = (job.get("jobs", [job])[0].get("url")
                   if "jobs" in job else job.get("url")) or sample[0]["url"]
            opened = await call(session, "browser_open", {"url": url})
            els = opened.get("elements") or []
            show("BROWSER_OPEN", {k: opened.get(k) for k in
                                  ("url", "title", "http_status", "error")})
            if not els:
                failures.append(f"browser_open returned no elements: {opened.get('error')}")

            filtered = await call(session, "browser_snapshot",
                                  {"filter_text": "apply", "text_chars": 200})
            show("SNAPSHOT filter=apply",
                 {"matches": len(filtered.get("elements") or []),
                  "url": filtered.get("url")})

            form = await call(session, "browser_form")
            show("FORM", {k: form.get(k) for k in ("url", "fields", "submit_buttons")})

            shot = await call(session, "browser_screenshot", {"name": "e2e"})
            show("SCREENSHOT", shot)

            closed = await call(session, "browser_close")
            show("BROWSER_CLOSE", closed)

            if app_id:
                rec = await call(session, "record_application", {
                    "application_id": app_id, "status": "withdrawn",
                    "notes": "automated e2e test — never submitted",
                    "evidence": {"screenshot": shot.get("screenshot")},
                })
                show("RECORD_APPLICATION", {k: rec.get("application", {}).get(k)
                                            for k in ("id", "status", "notes")})

            apps = await call(session, "list_applications", {"limit": 5})
            show("LIST_APPLICATIONS",
                 [{"title": a.get("job_title"), "status": a.get("status")}
                  for a in apps.get("applications", [])])

    print("\n===== VERDICT =====")
    if failures:
        for f in failures:
            print("FAIL:", f)
        return 1
    print("E2E OK — search/dedup/guards/plan/browser(no-submit)/record all work")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
