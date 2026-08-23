"""Probe gov.uk Find a Job via real Edge browser."""
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
            await call(s, "browser_wait", {"seconds": 3})
            d = await call(s, "browser_eval", {"js":
                "() => ({url: location.href, title: document.title, "
                "forms: Array.from(document.forms).map(f=>f.action), "
                "inputs: Array.from(document.querySelectorAll('input')).map(i=>"
                "({type:i.type,name:i.name,placeholder:i.placeholder,id:i.id})), "
                "buttons: Array.from(document.querySelectorAll('button')).map(b=>"
                "b.innerText.trim().slice(0,40)), "
                "headings: Array.from(document.querySelectorAll('h1,h2')).map(h=>"
                "h.innerText.trim().slice(0,60)), "
                "text: (document.body.innerText||'').replace(/\\s+/g,' ').slice(0,800)})"
            })
            print("=== FIND A JOB ===")
            print(json.dumps(d.get("result"), indent=1, ensure_ascii=False))

            # try searching
            inp = [i for i in (d.get("result", {}) or {}).get("inputs", [])
                   if "keyword" in (i.get("name") or "").lower()
                   or "search" in (i.get("name") or "").lower()
                   or "keyword" in (i.get("placeholder") or "").lower()]
            btn = [b for b in (d.get("result", {}) or {}).get("buttons", [])
                   if "search" in b.lower()]
            print("search inputs:", inp)
            print("search buttons:", btn)

            # snapshot for element numbers
            snap = await call(s, "browser_snapshot", {"text_chars": 500})
            els = snap.get("elements") or []
            for e in els[:15]:
                print("  ", e["n"], e["tag"], e.get("type"),
                      repr((e.get("name") or "")[:50]))

            await call(s, "browser_close")


asyncio.run(main())
