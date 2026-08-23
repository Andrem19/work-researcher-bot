"""Open CV-Library /login in the automation profile and WAIT while the user
types email+password manually (no Google SSO on this board). Polls until the
login form disappears, then confirms the session."""

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


async def main() -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "work_researcher", "serve", "--transport", "stdio"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            await call(s, "browser_open",
                       {"url": "https://www.cv-library.co.uk/login"})
            await call(s, "browser_wait", {"seconds": 2})
            print(">>> ENTER YOUR CV-LIBRARY EMAIL + PASSWORD IN THE OPEN "
                  "WINDOW NOW — waiting up to 5 minutes...", flush=True)
            deadline = asyncio.get_event_loop().time() + 300
            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(6)
                d = await call(s, "browser_snapshot", {"text_chars": 800})
                els = d.get("elements") or []
                text = (d.get("text") or "").lower()
                url = d.get("url") or ""
                has_pw = any(e.get("type") == "password" for e in els)
                on_login = "/login" in url or "login to start" in text
                if not has_pw and not on_login:
                    print("CV-LIBRARY LOGIN COMPLETE")
                    print("url:", url)
                    print("text head:", text[:200])
                    await call(s, "browser_screenshot", {"name": "cvl-login-complete"})
                    # agent's own verdict afterwards
                    v = await call(s, "browser_login",
                                   {"url": "https://www.cv-library.co.uk"})
                    print("browser_login now says:",
                          json.dumps({k: v.get(k) for k in
                                      ("logged_in", "needs_user", "note")},
                                     ensure_ascii=False))
                    await call(s, "browser_close")
                    return 0
            print("TIMEOUT — credentials were not entered in 5 minutes")
            await call(s, "browser_close")
            return 1


asyncio.run(main())
