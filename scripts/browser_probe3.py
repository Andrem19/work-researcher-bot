import asyncio

from playwright.async_api import async_playwright

TJ = "https://www.totaljobs.com/job/data-analyst/experis-job107876146"


async def try_nav(page, url):
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        print(url[:50], "->", resp.status if resp else None, "|", page.url[:70],
              "|", (await page.title())[:50])
    except Exception as exc:
        print(url[:50], "FAIL", type(exc).__name__, str(exc)[:160])


async def main():
    async with async_playwright() as pw:
        # headed chromium
        ctx = await pw.chromium.launch_persistent_context(
            r"D:\PYTHON\WORK_RESEARCHER_MCP\data\browser_probe_profile",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await try_nav(page, TJ)
        await ctx.close()

        # real Edge, headless
        ctx = await pw.chromium.launch_persistent_context(
            r"D:\PYTHON\WORK_RESEARCHER_MCP\data\browser_probe_profile_edge",
            channel="msedge",
            headless=True,
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await try_nav(page, TJ)
        await ctx.close()


asyncio.run(main())
