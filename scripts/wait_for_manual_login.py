"""Start the Google login on totaljobs and WAIT while the user types the
password in the visible window (up to 5 minutes), then report the final
login state. The profile keeps the session afterwards."""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = [sys.executable, "-m", "work_researcher", "serve", "--transport", "stdio"]


async def call(session, name, args=None):
    result = await session.call_tool(name, args or {})
    texts = [b.text for b in result.content if getattr(b, "type", "") == "text"]
    try:
        return json.loads(texts[0]) if texts else {}
    except (json.JSONDecodeError, IndexError):
        return {"raw": texts[0] if texts else None}


async def main() -> int:
    params = StdioServerParameters(command=SERVER[0], args=SERVER[1:])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            r = await call(s, "browser_login", {"url": "https://www.totaljobs.com"})
            print("initial:", json.dumps(
                {k: r.get(k) for k in ("logged_in", "needs_user", "note")}, indent=1))
            if r.get("logged_in"):
                print("ALREADY LOGGED IN")
                await call(s, "browser_close")
                return 0
            print(">>> TYPE THE GOOGLE PASSWORD FOR 7255591@gmail.com IN THE "
                  "OPEN WINDOW NOW — waiting up to 5 minutes...", flush=True)
            deadline = asyncio.get_event_loop().time() + 300
            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(6)
                snap = await call(s, "browser_snapshot", {"text_chars": 200})
                url = snap.get("url") or ""
                names = " ".join((e.get("name") or "").lower()
                                 for e in snap.get("elements") or [])
                text = (snap.get("text") or "").lower()
                still_google = "accounts.google.com" in url
                signed_out = any(m in names or m in text for m in
                                 ("sign in", "log in", "sign up"))
                if not still_google and not signed_out:
                    print("LOGIN COMPLETE — back on the board, signed in.")
                    await call(s, "browser_screenshot", {"name": "login-complete"})
                    await call(s, "browser_close")
                    return 0
                if not still_google and signed_out and "totaljobs" in url:
                    # board page but still signed out — maybe consent pending
                    print("  back on totaljobs but still signed out; "
                          "re-checking…", flush=True)
            print("TIMEOUT — the password was not entered in 5 minutes.")
            await call(s, "browser_close")
            return 1


asyncio.run(main())
