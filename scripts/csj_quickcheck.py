"""Pass the Civil Service Jobs 'Quick Check' anti-bot gate, then
inspect the real landing + search + sign-in pages."""

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


async def pass_quickcheck(s):
    d = await call(s, "browser_snapshot", {"text_chars": 600})
    text = (d.get("text") or "").lower()
    if "quick check" not in text and "i'm not a robot" not in text:
        return d
    els = d.get("elements") or []
    cb = next((e for e in els if e.get("type") == "checkbox"), None)
    if cb:
        await call(s, "browser_set", {"n": cb["n"], "value": True,
                                      "snapshot_after": False})
    btn = next((e for e in els if e["tag"] == "button"
               and "continue" in (e.get("name") or "").lower()), None)
    if btn:
        await call(s, "browser_click", {"n": btn["n"]})
    await call(s, "browser_wait", {"seconds": 3})
    return await call(s, "browser_snapshot", {"text_chars": 2000})


async def main():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "work_researcher", "serve", "--transport", "stdio"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            await call(s, "browser_open",
                       {"url": "https://www.civilservicejobs.service.gov.uk/landing"})
            await call(s, "browser_wait", {"seconds": 2})
            d = await pass_quickcheck(s)
            print("=== AFTER QUICK CHECK ===")
            print("url:", d.get("url"))
            print("title:", d.get("title"))
            text = (d.get("text") or "")[:500]
            print("text:", text)
            els = d.get("elements") or []
            print("elements:", len(els))
            for e in els[:20]:
                print("  ", e["n"], e["tag"], e.get("type"),
                      repr((e.get("name") or "")[:50]))

            # search
            search_el = next(
                (e for e in els if e["tag"] == "input"
                 and ("search" in (e.get("name") or "").lower()
                      or "keyword" in (e.get("name") or "").lower())), None)
            if search_el:
                await call(s, "browser_set", {"n": search_el["n"],
                                              "value": "data analyst",
                                              "snapshot_after": False})
                btn = next(
                    (e for e in els if e["tag"] == "button"
                    and "search" in (e.get("name") or "").lower()), None)
                if btn:
                    await call(s, "browser_click", {"n": btn["n"]})
                    await call(s, "browser_wait", {"seconds": 4})
                    d = await pass_quickcheck(s)
                    print("\n=== RESULTS ===")
                    print("url:", d.get("url"))
                    print("title:", d.get("title"))
                    els = d.get("elements") or []
                    job_links = [e for e in els if e["tag"] == "a"
                                 and "/job/" in (e.get("name") or "")]
                    print("job links:", len(job_links))
                    for e in els[:15]:
                        print("  ", e["n"], e["tag"],
                              repr((e.get("name") or "")[:55]))
                    text = (d.get("text") or "")[:600]
                    print("text:", text)
            else:
                print("no search input found")

            # sign-in page
            d = await call(s, "browser_open",
                           {"url": "https://www.civilservicejobs.service.gov.uk/account/signin"})
            await call(s, "browser_wait", {"seconds": 2})
            d = await pass_quickcheck(s)
            print("\n=== SIGN-IN ===")
            print("url:", d.get("url"))
            print("title:", d.get("title"))
            els = d.get("elements") or []
            print("elements:", len(els))
            for e in els[:15]:
                print("  ", e["n"], e["tag"], e.get("type"),
                      repr((e.get("name") or "")[:50]))
            print("google SSO:", any("google" in (e.get("name") or "").lower()
                                     for e in els))
            await call(s, "browser_screenshot", {"name": "csj-after-check"})
            await call(s, "browser_close")


asyncio.run(main())
