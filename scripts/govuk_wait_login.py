"""Open the GOV.UK One Login page and wait for the user to sign in
manually (email + confirmation code, no Google SSO on gov.uk).
The session persists in the Edge profile afterwards."""
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
            # open the Work Hub login page
            await call(s, "browser_open",
                       {"url": "https://www.jobs.service.gov.uk/auth/login"})
            print(">>> SIGN IN with your GOV.UK One Login in the open window")
            print(">>> (email + code from your phone/email)")
            print(">>> Waiting up to 5 minutes...", flush=True)

            deadline = asyncio.get_event_loop().time() + 300
            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(6)
                d = await call(s, "browser_eval", {"js":
                    "() => ({url: location.href, "
                    "text: (document.body.innerText||'').replace(/\\s+/g,' ')"
                    "  .slice(0, 200)})"})
                url = (d.get("result") or {}).get("url", "")
                text = (d.get("result") or {}).get("text", "").lower()
                # success: back on Work Hub (not auth/login or signin.account.gov.uk)
                if ("jobs.service.gov.uk" in url
                        and "/auth/" not in url
                        and "signin.account.gov.uk" not in url
                        and "sign in" not in text):
                    print("LOGIN COMPLETE")
                    print("url:", url)
                    print("text:", text[:200])
                    # verify with /account/jobs
                    d = await call(s, "browser_open",
                                   {"url": "https://www.jobs.service.gov.uk/account/jobs"})
                    await call(s, "browser_wait", {"seconds": 3})
                    d = await call(s, "browser_eval", {"js":
                        "() => ({url: location.href, title: document.title, "
                        "text: (document.body.innerText||'').replace(/\\s+/g,' ')"
                        "  .slice(0, 300)})"})
                    print("account/jobs:", json.dumps(d.get("result"),
                                                        ensure_ascii=False))
                    await call(s, "browser_screenshot",
                               {"name": "govuk-loggedin"})
                    await call(s, "browser_close")
                    return 0
            print("TIMEOUT — login not completed in 5 minutes")
            await call(s, "browser_close")
            return 1


asyncio.run(main())
