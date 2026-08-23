"""Interactive Quick Check pass: open the page, click the checkbox, wait
for the user to solve any challenge and reach the real site, then dump
the landing + search + signin structure."""

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
            await call(s, "browser_open",
                       {"url": "https://www.civilservicejobs.service.gov.uk/landing"})
            print(">>> If a Quick Check / captcha appears, SOLVE IT in the")
            print(">>> open Edge window, then tell me. Waiting up to 3 min...")
            deadline = asyncio.get_event_loop().time() + 180
            passed = False
            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(5)
                d = await call(s, "browser_snapshot", {"text_chars": 300})
                text = (d.get("text") or "").lower()
                if "quick check" not in text and "robot" not in text:
                    passed = True
                    break
            if not passed:
                print("TIMEOUT — Quick Check not passed")
                await call(s, "browser_close")
                return 1
            print("QUICK CHECK PASSED")
            print("url:", d.get("url"))
            print("title:", d.get("title"))
            text = (d.get("text") or "")[:600]
            print("text:", text)
            els = d.get("elements") or []
            print("elements:", len(els))
            for e in els[:20]:
                print("  ", e["n"], e["tag"], e.get("type"),
                      repr((e.get("name") or "")[:55]))

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
                    d = await call(s, "browser_snapshot", {"text_chars": 2000})
                    print("\n=== RESULTS ===")
                    print("url:", d.get("url"))
                    print("title:", d.get("title"))
                    els = d.get("elements") or []
                    job_links = [e for e in els if e["tag"] == "a"
                                 and "/job/" in (e.get("name") or "")]
                    print("job links:", len(job_links))
                    text = (d.get("text") or "")[:700]
                    print("text:", text)
                    for e in els[:15]:
                        print("  ", e["n"], e["tag"],
                              repr((e.get("name") or "")[:55]))
            else:
                print("no search input found")

            # sign-in page
            d = await call(s, "browser_open",
                           {"url": "https://www.civilservicejobs.service.gov.uk/account/signin"})
            await call(s, "browser_wait", {"seconds": 3})
            d = await call(s, "browser_snapshot", {"text_chars": 1500})
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
            await call(s, "browser_screenshot", {"name": "csj-real"})
            await call(s, "browser_close")


asyncio.run(main())
