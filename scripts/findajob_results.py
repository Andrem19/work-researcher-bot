"""Search gov.uk Work Hub via direct form fill + submit, then dump
the results page structure: job cards, titles, companies, locations."""
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
            await call(s, "browser_open", {"url": "https://www.gov.uk/find-a-job"})
            await call(s, "browser_wait", {"seconds": 2})
            # click Start now
            snap = await call(s, "browser_snapshot", {"text_chars": 200})
            start = next((e for e in snap.get("elements") or []
                          if "start now" in (e.get("name") or "").lower()), None)
            if start:
                await call(s, "browser_click", {"n": start["n"]})
                await call(s, "browser_wait", {"seconds": 4})

            # dismiss cookies
            await call(s, "browser_eval", {"js":
                "() => { const b=document.querySelector('button[name=accept]'); "
                "if(b) b.click(); }"})
            await call(s, "browser_wait", {"seconds": 1})

            # fill keywords + submit via JS
            await call(s, "browser_eval", {"js":
                "() => { const i=document.getElementById('keywordsInput'); "
                "if(i){i.value='data analyst'; "
                "i.closest('form').submit();} }"})
            await call(s, "browser_wait", {"seconds": 5})

            d = await call(s, "browser_eval", {"js":
                "() => ({url: location.href, title: document.title, "
                "jobLinks: Array.from(document.querySelectorAll('a')).filter(a => "
                "a.href.includes('/job/')).map(a => "
                "{href:a.href, text:a.innerText.trim().slice(0,100)}).slice(0,15), "
                "headings: Array.from(document.querySelectorAll('h1,h2,h3')).map(h => "
                "h.innerText.trim().slice(0,80)), "
                "text: (document.body.innerText||'').replace(/\\s+/g,' ').slice(0,2000)})"
            })
            print("=== RESULTS ===")
            print(json.dumps(d.get("result"), indent=1, ensure_ascii=False))

            # snapshot for element numbers
            snap = await call(s, "browser_snapshot", {"text_chars": 2000})
            els = snap.get("elements") or []
            print("\nelements:", len(els))
            for e in els[:25]:
                print("  ", e["n"], e["tag"],
                      repr((e.get("name") or "")[:70]))

            await call(s, "browser_screenshot", {"name": "findajob-results2"})
            await call(s, "browser_close")


asyncio.run(main())
