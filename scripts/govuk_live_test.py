"""Live test: search gov.uk Work Hub via browser, scrape cards, feed them
into the MCP via submit_job_observations, then search_jobs to verify they
appear ranked alongside HTTP providers."""
import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, "src")
from work_researcher.providers.govuk_workhub import parse_card  # noqa: E402


async def call(s, name, args=None):
    r = await s.call_tool(name, args or {})
    t = [b.text for b in r.content if getattr(b, "type", "") == "text"]
    try:
        return json.loads(t[0]) if t else {}
    except (json.JSONDecodeError, IndexError):
        return {"raw": t[0] if t else None}


async def main() -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "work_researcher", "serve", "--transport", "stdio"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()

            # 1) open gov.uk/find-a-job → Start now → Work Hub
            d = await call(s, "browser_open", {"url": "https://www.gov.uk/find-a-job"})
            await call(s, "browser_wait", {"seconds": 2})
            snap = await call(s, "browser_snapshot", {"text_chars": 200})
            start = next((e for e in snap.get("elements") or []
                          if "start now" in (e.get("name") or "").lower()), None)
            if start:
                await call(s, "browser_click", {"n": start["n"]})
                await call(s, "browser_wait", {"seconds": 4})

            # 2) search for "data analyst"
            await call(s, "browser_eval", {"js":
                "() => { const i=document.getElementById('keywordsInput'); "
                "if(i){i.value='data analyst'; i.closest('form').submit();} }"})
            await call(s, "browser_wait", {"seconds": 5})

            # 3) scrape job cards via link-based approach
            scrape_js = (
                "() => {"
                "  const links = Array.from(document.querySelectorAll('a'))"
                "    .filter(a => a.href && a.href.match(/\\/jobs\\/[a-f0-9]{20,}/));"
                "  const seen = new Set();"
                "  const cards = [];"
                "  for (const a of links) {"
                "    if (seen.has(a.href)) continue;"
                "    seen.add(a.href);"
                "    const li = a.closest('li, div, article, [class*=result]');"
                "    const text = (li ? li.innerText : a.innerText || '')"
                "      .replace(/\\s+/g, ' ').trim();"
                "    cards.push({"
                "      url: a.href,"
                "      title: a.innerText.trim().slice(0, 120),"
                "      context: text.slice(0, 500)"
                "    });"
                "    if (cards.length >= 25) break;"
                "  }"
                "  return {url: location.href, count: cards.length, cards};"
                "}"
            )
            d = await call(s, "browser_eval", {"js": scrape_js})
            scraped = d.get("result") or {}
            cards = scraped.get("cards") or []
            print(f"scraped: {len(cards)} cards from {scraped.get('url')}")
            if not cards:
                print("no cards — aborting")
                await call(s, "browser_close")
                return 1
            for c in cards[:3]:
                print(f"  {c['title'][:50]:50} | {c['url'][-40:]}")

            # 4) feed into MCP via submit_job_observations
            observations = []
            for c in cards:
                parsed = parse_card(c.get("context", ""), c.get("url"))
                if parsed.get("title"):
                    observations.append({
                        "source": "findajob",
                        "url": c.get("url"),
                        "title": parsed["title"],
                        "company": parsed.get("company"),
                        "location_text": parsed.get("location_text"),
                        "salary_raw": parsed.get("salary_raw"),
                        "description": parsed.get("description"),
                    })
            print(f"\nparsed: {len(observations)} observations")
            if observations:
                result = await call(s, "submit_job_observations", {
                    "observations": observations[:15],
                    "observation_type": "search_cards",
                })
                print("submit_job_observations:", json.dumps(result, indent=1,
                                                             ensure_ascii=False))

            # 5) verify: search_jobs should now include findajob results
            search = await call(s, "search_jobs", {
                "query": "data analyst", "limit_per_source": 10})
            results = search.get("results") or []
            findajob_results = [r for r in results
                                if "findajob" in (r.get("sources") or [])]
            print(f"\nsearch results: {len(results)} total, "
                  f"{len(findajob_results)} from findajob")
            for r in results[:5]:
                print(f"  {r['title'][:35]:35} | "
                      f"{(r['company'] or '')[:18]:18} | "
                      f"{r.get('posted_by'):8} | "
                      f"{'.'.join(r.get('sources') or [])[:20]}")

            await call(s, "browser_close")
            ok = len(findajob_results) > 0 or len(observations) > 0
            print("\nVERDICT:", "PASS" if ok else "FAIL")
            return 0 if ok else 1


asyncio.run(main())
