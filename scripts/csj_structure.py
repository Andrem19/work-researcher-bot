"""After passing Quick Check, dump the real DOM structure: forms,
inputs, buttons, headings, links — to find the search and sign-in forms
(which are JS-rendered and don't appear in the element snapshot)."""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def call(session, name, args=None):
    result = await session.call_tool(name, args or {})
    texts = [b.text for b in result.content if getattr(b, "type", "") == "text"]
    try:
        return json.loads(texts[0]) if texts else {}
    except (json.JSONDecodeError, IndexError):
        return {"raw": texts[0] if texts else None}


async def main():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "work_researcher", "serve", "--transport", "stdio"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()

            # pass Quick Check
            await call(s, "browser_open",
                       {"url": "https://www.civilservicejobs.service.gov.uk/landing"})
            await call(s, "browser_wait", {"seconds": 2})
            d = await call(s, "browser_snapshot", {"text_chars": 200})
            if "quick check" in (d.get("text") or "").lower():
                cb = next((e for e in d.get("elements") or []
                           if e.get("type") == "checkbox"), None)
                if cb:
                    await call(s, "browser_set", {"n": cb["n"], "value": True,
                                                  "snapshot_after": False})
                btn = next((e for e in d.get("elements") or []
                             if e["tag"] == "button"
                             and "continue" in (e.get("name") or "").lower()), None)
                if btn:
                    await call(s, "browser_click", {"n": btn["n"]})
                await call(s, "browser_wait", {"seconds": 4})

            # now inspect the REAL landing DOM
            d = await call(s, "browser_eval", {"js":
                "() => ({url: location.href, title: document.title, "
                "forms: Array.from(document.forms).map(f => f.action), "
                "inputs: Array.from(document.querySelectorAll('input')).map(i => "
                "({type: i.type, name: i.name, placeholder: i.placeholder, "
                "id: i.id})), "
                "buttons: Array.from(document.querySelectorAll('button')).map(b => "
                "b.innerText.trim().slice(0,40)), "
                "headings: Array.from(document.querySelectorAll('h1,h2')).map(h => "
                "h.innerText.trim().slice(0,60)), "
                "text: (document.body.innerText||'').replace(/\\s+/g,' ').slice(0,800)})"
            })
            print("=== LANDING DOM ===")
            print(json.dumps(d.get("result"), indent=1, ensure_ascii=False))

            # sign-in page DOM
            await call(s, "browser_open",
                       {"url": "https://www.civilservicejobs.service.gov.uk/account/signin"})
            await call(s, "browser_wait", {"seconds": 3})
            d = await call(s, "browser_eval", {"js":
                "() => ({url: location.href, title: document.title, "
                "forms: Array.from(document.forms).map(f => ({action: f.action, "
                "method: f.method})), "
                "inputs: Array.from(document.querySelectorAll('input')).map(i => "
                "({type: i.type, name: i.name, placeholder: i.placeholder, "
                "id: i.id, ariaLabel: i.getAttribute('aria-label')})), "
                "buttons: Array.from(document.querySelectorAll('button')).map(b => "
                "b.innerText.trim().slice(0,40)), "
                "links: Array.from(document.querySelectorAll('a')).filter(a => "
                "a.href.includes('google')||a.href.includes('signin')||"
                "a.href.includes('register')).map(a => "
                "({href: a.href, text: a.innerText.trim().slice(0,50)})), "
                "text: (document.body.innerText||'').replace(/\\s+/g,' ').slice(0,600)})"
            })
            print("\n=== SIGN-IN DOM ===")
            print(json.dumps(d.get("result"), indent=1, ensure_ascii=False))
            await call(s, "browser_screenshot", {"name": "csj-structure"})
            await call(s, "browser_close")


asyncio.run(main())
