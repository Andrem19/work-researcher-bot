"""Dump full job cards from gov.uk Work Hub search results."""
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
            snap = await call(s, "browser_snapshot", {"text_chars": 200})
            start = next((e for e in snap.get("elements") or []
                          if "start now" in (e.get("name") or "").lower()), None)
            if start:
                await call(s, "browser_click", {"n": start["n"]})
                await call(s, "browser_wait", {"seconds": 4})
            # fill keywords + submit
            await call(s, "browser_eval", {"js":
                "() => { const i=document.getElementById('keywordsInput'); "
                "if(i){i.value='data analyst'; i.closest('form').submit();} }"})
            await call(s, "browser_wait", {"seconds": 5})

            # dump job cards with full detail
            d = await call(s, "browser_eval", {"js":
                "() => { "
                "  const cards = document.querySelectorAll('[data-test-id], "
                "    .job-result, .search-result, li[class*=job], article, "
                "    .govuk-summary-list__row, [class*=JobCard]');"
                "  const jobLinks = Array.from(document.querySelectorAll('a'))"
                "    .filter(a => a.href.includes('/job/'));"
                "  return {"
                "    cardCount: cards.length,"
                "    jobLinkCount: jobLinks.length,"
                "    jobLinks: jobLinks.slice(0,15).map(a => "
                "      {href:a.href, text:a.innerText.trim().slice(0,100),"
                "       parent: a.closest('li,div,article')?.innerText"
                "         ?.replace(/\\s+/g,' ').slice(0,300)})"
                "  }"
                "}"
            })
            print(json.dumps(d.get("result"), indent=1, ensure_ascii=False))

            # also get the page text to see how results are structured
            d = await call(s, "browser_eval", {"js":
                "() => (document.body.innerText||'').replace(/\\s+/g,' ')"
                "  .slice(0, 3000)"})
            print("\n=== PAGE TEXT ===")
            print(d.get("result"))

            await call(s, "browser_screenshot", {"name": "findajob-cards"})
            await call(s, "browser_close")


asyncio.run(main())
