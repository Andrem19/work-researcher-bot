"""Inspect the actual results page DOM structure to find job card selectors."""
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
            await call(s, "browser_eval", {"js":
                "() => { const i=document.getElementById('keywordsInput'); "
                "if(i){i.value='data analyst'; i.closest('form').submit();} }"})
            await call(s, "browser_wait", {"seconds": 5})

            d = await call(s, "browser_eval", {"js":
                "() => {"
                "  const allLinks = Array.from(document.querySelectorAll('a'));"
                "  const jobLinks = allLinks.filter(a => a.href.includes('/job/'));"
                "  const allHrefs = allLinks.map(a => a.href).filter(h => "
                "    h.includes('job') || h.includes('vacancy') || "
                "    h.includes('detail')).slice(0, 20);"
                "  const classSamples = Array.from(document.querySelectorAll("
                "    '[class]')).map(e => e.className).filter(c => "
                "    typeof c === 'string' && (c.includes('job') || "
                "    c.includes('result') || c.includes('card') || "
                "    c.includes('vacancy'))).slice(0, 15);"
                "  const liTexts = Array.from(document.querySelectorAll('li'))"
                "    .map(li => li.innerText.replace(/\\s+/g,' ').trim().slice(0,200))"
                "    .filter(t => t.length > 30).slice(0, 5);"
                "  return {url: location.href, totalLinks: allLinks.length, "
                "    jobLinks: jobLinks.length, "
                "    jobHrefs: jobLinks.map(a => a.href).slice(0, 5),"
                "    allJobishHrefs: allHrefs,"
                "    classSamples: classSamples,"
                "    liTexts: liTexts,"
                "    text: (document.body.innerText||'').replace(/\\s+/g,' ')"
                "      .slice(0, 2000)"
                "  }"
                "}"
            })
            print(json.dumps(d.get("result"), indent=1, ensure_ascii=False))
            await call(s, "browser_close")


asyncio.run(main())
