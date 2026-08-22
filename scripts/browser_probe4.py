import asyncio

from playwright.async_api import async_playwright

TJ = "https://www.totaljobs.com/job/data-analyst/experis-job107876146"
REED = "https://www.reed.co.uk/jobs/data-analyst/57260576"


async def try_nav(page, url):
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        title = await page.title()
        print(url[:55], "->", resp.status if resp else None, "|", title[:60])
    except Exception as exc:
        print(url[:55], "FAIL", type(exc).__name__, str(exc)[:150])


async def main():
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            r"D:\PYTHON\WORK_RESEARCHER_MCP\data\browser_probe_profile_edge",
            channel="msedge",
            headless=True,
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await try_nav(page, "https://example.com")
        await try_nav(page, TJ)
        await try_nav(page, REED)
        await ctx.close()


asyncio.run(main())
