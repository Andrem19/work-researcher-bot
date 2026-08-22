import asyncio

from playwright.async_api import async_playwright


async def main():
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(
            r"D:\PYTHON\WORK_RESEARCHER_MCP\data\browser_profile",
            channel="msedge", headless=False,
        )
        page = ctx.pages[-1] if ctx.pages else await ctx.new_page()
        await page.goto("https://www.totaljobs.com/en-GB/candidate/login",
                        wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)
        print("url:", page.url)
        print("frames:", [f.url for f in page.frames])
        for f in page.frames:
            try:
                n = await f.locator(
                    "button:has-text('Google'), a:has-text('Google')").count()
                if n:
                    texts = await f.locator(
                        "button:has-text('Google'), a:has-text('Google')").all_inner_texts()
                    print(f"  google controls in {f.url[:60]}:", texts[:3])
            except Exception as exc:  # noqa: BLE001
                print("  frame error:", str(exc)[:80])
        body = (await page.locator("button, a").all_inner_texts())
        print("page buttons sample:", [t.strip() for t in body if t.strip()][:15])
        await ctx.close()


asyncio.run(main())
