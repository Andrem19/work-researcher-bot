"""Click Start now on gov.uk/find-a-job, then search for 'data analyst'
and inspect the results page structure: job cards, links, pagination."""
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
            d = await call(s, "browser_open", {"url": "https://www.gov.uk/find-a-job"})
            await call(s, "browser_wait", {"seconds": 2})
            snap = await call(s, "browser_snapshot", {"text_chars": 200})
            start = next((e for e in snap.get("elements") or []
                          if "start now" in (e.get("name") or "").lower()), None)
            if start:
                await call(s, "browser_click", {"n": start["n"]})
                await call(s, "browser_wait", {"seconds": 4})
            d = await call(s, "browser_eval", {"js":
                "() => ({url: location.href, title: document.title, "
                "forms: Array.from(document.forms).map(f=>f.action), "
                "inputs: Array.from(document.querySelectorAll('input')).map(i=>"
                "({type:i.type,name:i.name,placeholder:i.placeholder,id:i.id})), "
                "headings: Array.from(document.querySelectorAll('h1,h2')).map(h=>"
                "h.innerText.trim().slice(0,60)), "
                "text: (document.body.innerText||'').replace(/\\s+/g,' ').slice(0,600)})"
            })
            print("=== SEARCH PAGE ===")
            print(json.dumps(d.get("result"), indent=1, ensure_ascii=False))

            # find the keyword search input and search button
            r = d.get("result", {}) or {}
            snap = await call(s, "browser_snapshot", {"text_chars": 300})
            els = snap.get("elements") or []
            search_el = next((e for e in els if e["tag"] == "input"
                              and "keyword" in (e.get("name") or "").lower()), None)
            search_btn = next((e for e in els if e["tag"] == "button"
                               and "search" in (e.get("name") or "").lower()), None)
            print("search_el:", search_el, "| search_btn:", search_btn)

            if search_el and search_btn:
                await call(s, "browser_set", {"n": search_el["n"],
                                              "value": "data analyst",
                                              "snapshot_after": False})
                await call(s, "browser_click", {"n": search_btn["n"]})
                await call(s, "browser_wait", {"seconds": 5})
                d = await call(s, "browser_eval", {"js":
                    "() => ({url: location.href, title: document.title, "
                    "jobLinks: Array.from(document.querySelectorAll('a')).filter(a => "
                    "a.href.includes('/job/')).map(a => "
                    "{href:a.href, text:a.innerText.trim().slice(0,80)}).slice(0,10), "
                    "headings: Array.from(document.querySelectorAll('h1,h2,h3')).map(h => "
                    "h.innerText.trim().slice(0,80)), "
                    "text: (document.body.innerText||'').replace(/\\s+/g,' ').slice(0,1500)})"
                })
                print("\n=== RESULTS ===")
                print(json.dumps(d.get("result"), indent=1, ensure_ascii=False))
                # snapshot elements
                snap = await call(s, "browser_snapshot", {"text_chars": 1500})
                els = snap.get("elements") or []
                print("\nelements:", len(els))
                for e in els[:25]:
                    print("  ", e["n"], e["tag"],
                          repr((e.get("name") or "")[:65]))

            await call(s, "browser_screenshot", {"name": "findajob-results"})
            await call(s, "browser_close")


asyncio.run(main())
