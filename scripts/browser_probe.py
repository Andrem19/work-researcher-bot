import asyncio

from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            r"D:\PYTHON\WORK_RESEARCHER_MCP\data\browser_probe_profile",
            headless=True,
            viewport={"width": 1440, "height": 900},
            locale="en-GB",
        )
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        for url in [
            "https://www.totaljobs.com/job/data-analyst/experis-job107876146",
            "https://www.reed.co.uk/jobs/data-analyst/57260576",
            "https://example.com",
        ]:
            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                print(url, "->", resp.status if resp else None, "|", page.url[:80],
                      "|", (await page.title())[:60])
            except Exception as exc:
                print(url, "FAIL", type(exc).__name__, str(exc)[:200])
        await ctx.close()


asyncio.run(main())
