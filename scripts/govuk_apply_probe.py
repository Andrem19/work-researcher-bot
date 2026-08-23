"""Probe the gov.uk Work Hub application flow:
1) check login state via /account/jobs
2) open a real job page and inspect the apply button + form structure
3) if apply opens, dump form fields, file inputs, submit buttons"""
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

            # 1) check login via /account/jobs
            d = await call(s, "browser_open",
                           {"url": "https://www.jobs.service.gov.uk/account/jobs"})
            await call(s, "browser_wait", {"seconds": 3})
            d = await call(s, "browser_eval", {"js":
                "() => ({url: location.href, title: document.title, "
                "text: (document.body.innerText||'').replace(/\\s+/g,' ').slice(0,400)})"
            })
            print("=== LOGIN CHECK ===")
            print(json.dumps(d.get("result"), indent=1, ensure_ascii=False))

            # 2) search for a job to get a real job URL
            await call(s, "browser_open",
                       {"url": "https://www.gov.uk/find-a-job"})
            await call(s, "browser_wait", {"seconds": 2})
            snap = await call(s, "browser_snapshot", {"text_chars": 200})
            start = next((e for e in snap.get("elements") or []
                          if "start now" in (e.get("name") or "").lower()), None)
            if start:
                await call(s, "browser_click", {"n": start["n"]})
                await call(s, "browser_wait", {"seconds": 4})
            await call(s, "browser_eval", {"js":
                "() => { const i=document.getElementById('keywordsInput'); "
                "if(i){i.value='data analyst'; i.closest('form').submit();} }"})
            await call(s, "browser_wait", {"seconds": 5})

            # get first job link
            d = await call(s, "browser_eval", {"js":
                "() => { const l = Array.from(document.querySelectorAll('a'))"
                "  .filter(a => a.href.match(/\\/jobs\\/[a-f0-9]{20,}/));"
                "  return l.length > 0 ? l[0].href : null; }"})
            job_url = d.get("result")
            print(f"\njob url: {job_url}")
            if not job_url:
                print("no job URL found")
                await call(s, "browser_close")
                return

            # 3) open the job page
            d = await call(s, "browser_open", {"url": job_url})
            await call(s, "browser_wait", {"seconds": 4})
            d = await call(s, "browser_eval", {"js":
                "() => ({url: location.href, title: document.title, "
                "forms: Array.from(document.forms).map(f => ({action: f.action, "
                "method: f.method})), "
                "inputs: Array.from(document.querySelectorAll('input,textarea,select'))"
                "  .map(i => ({tag: i.tagName.toLowerCase(), type: i.type, "
                "    name: i.name, id: i.id, placeholder: i.placeholder, "
                "    ariaLabel: i.getAttribute('aria-label')})), "
                "buttons: Array.from(document.querySelectorAll('button,a'))"
                "  .filter(b => /apply|submit|start|continue|sign in/i"
                "    .test(b.innerText)).map(b => "
                "    {tag: b.tagName.toLowerCase(), text: b.innerText.trim().slice(0,50),"
                "     href: b.href || null}).slice(0, 10), "
                "headings: Array.from(document.querySelectorAll('h1,h2,h3'))"
                "  .map(h => h.innerText.trim().slice(0, 80)), "
                "text: (document.body.innerText||'').replace(/\\s+/g,' ').slice(0, 1500)})"
            })
            print("\n=== JOB PAGE ===")
            print(json.dumps(d.get("result"), indent=1, ensure_ascii=False))

            # snapshot elements
            snap = await call(s, "browser_snapshot", {"text_chars": 1500})
            els = snap.get("elements") or []
            print(f"\nelements: {len(els)}")
            apply_els = [e for e in els
                        if any(w in (e.get("name") or "").lower()
                               for w in ("apply", "submit", "start", "continue",
                                         "sign in"))]
            print("apply-ish:", [(e["n"], e["tag"], e.get("name")[:40]) for e in apply_els[:5]])

            # 4) try clicking Apply/Start
            if apply_els:
                clicked = await call(s, "browser_click", {"n": apply_els[0]["n"]})
                await call(s, "browser_wait", {"seconds": 4})
                d = await call(s, "browser_eval", {"js":
                    "() => ({url: location.href, title: document.title, "
                    "forms: Array.from(document.forms).map(f => ({action: f.action, "
                    "method: f.method})), "
                    "inputs: Array.from(document.querySelectorAll('input,textarea,select'))"
                    "  .map(i => ({tag: i.tagName.toLowerCase(), type: i.type, "
                    "    name: i.name, id: i.id, "
                    "    ariaLabel: i.getAttribute('aria-label')})), "
                    "buttons: Array.from(document.querySelectorAll('button'))"
                    "  .map(b => b.innerText.trim().slice(0,40)), "
                    "fileInputs: Array.from(document.querySelectorAll('input[type=file]'))"
                    "  .map(i => ({id: i.id, name: i.name, accept: i.accept, "
                    "    multiple: i.multiple})), "
                    "text: (document.body.innerText||'').replace(/\\s+/g,' ').slice(0, 1200)})"
                })
                print("\n=== AFTER APPLY CLICK ===")
                print(json.dumps(d.get("result"), indent=1, ensure_ascii=False))

            await call(s, "browser_screenshot", {"name": "govuk-apply"})
            await call(s, "browser_close")


asyncio.run(main())
