"""Now that the GOV.UK One Login session is active, open a real job page,
click Apply for this job, and dump the application form structure."""
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

            # open a known job page (Data Analyst, NHS Jobs)
            job_url = "https://www.jobs.service.gov.uk/jobs/6a82ca5315af0e0277dcec89"
            d = await call(s, "browser_open", {"url": job_url})
            await call(s, "browser_wait", {"seconds": 4})
            snap = await call(s, "browser_snapshot", {"text_chars": 2000})
            els = snap.get("elements") or []
            print(f"job page elements: {len(els)}")
            apply_els = [e for e in els
                         if "apply" in (e.get("name") or "").lower()]
            print("apply buttons:",
                  [(e["n"], e["tag"], e.get("name")[:40]) for e in apply_els])

            if apply_els:
                # click Apply
                clicked = await call(s, "browser_click", {"n": apply_els[0]["n"]})
                await call(s, "browser_wait", {"seconds": 5})
                d = await call(s, "browser_eval", {"js":
                    "() => ({url: location.href, title: document.title, "
                    "forms: Array.from(document.forms).map(f => ({action: f.action, "
                    "method: f.method})), "
                    "inputs: Array.from(document.querySelectorAll('input,textarea,select'))"
                    "  .map(i => ({tag: i.tagName.toLowerCase(), type: i.type, "
                    "    name: i.name, id: i.id, "
                    "    ariaLabel: i.getAttribute('aria-label'),"
                    "    required: i.required})), "
                    "buttons: Array.from(document.querySelectorAll('button'))"
                    "  .map(b => b.innerText.trim().slice(0,40)), "
                    "fileInputs: Array.from(document.querySelectorAll('input[type=file]'))"
                    "  .map(i => ({id: i.id, name: i.name, accept: i.accept, "
                    "    multiple: i.multiple})), "
                    "textareas: Array.from(document.querySelectorAll('textarea'))"
                    "  .map(t => ({name: t.name, id: t.id, "
                    "    placeholder: t.placeholder, "
                    "    ariaLabel: t.getAttribute('aria-label')})), "
                    "headings: Array.from(document.querySelectorAll('h1,h2,h3'))"
                    "  .map(h => h.innerText.trim().slice(0, 80)), "
                    "text: (document.body.innerText||'').replace(/\\s+/g,' ')"
                    "  .slice(0, 2000)})"
                })
                print("\n=== APPLICATION FORM ===")
                print(json.dumps(d.get("result"), indent=1, ensure_ascii=False))

                # snapshot for element numbers
                snap = await call(s, "browser_snapshot", {"text_chars": 2000})
                els = snap.get("elements") or []
                print(f"\nform elements: {len(els)}")
                for e in els[:25]:
                    print(f"  {e['n']} {e['tag']} {e.get('type','')} "
                          f"req={e.get('required','')} "
                          f"{repr((e.get('name') or '')[:50])}")

            await call(s, "browser_screenshot", {"name": "govuk-apply-form"})
            await call(s, "browser_close")


asyncio.run(main())
