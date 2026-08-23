"""Log into CV-Library in the automation profile.

Credentials come from environment variables (never hardcode them here —
this folder is a git repo):

    set CVL_EMAIL=...
    set CVL_PASSWORD=...
    uv run python scripts/cvl_autologin.py

One-time action; the session persists in the persistent Edge profile.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

EMAIL = os.environ.get("CVL_EMAIL", "")
PASSWORD = os.environ.get("CVL_PASSWORD", "")


async def call(session, name, args=None):
    result = await session.call_tool(name, args or {})
    texts = [b.text for b in result.content if getattr(b, "type", "") == "text"]
    try:
        return json.loads(texts[0]) if texts else {}
    except (json.JSONDecodeError, IndexError):
        return {"raw": texts[0] if texts else None}


async def main() -> int:
    if not (EMAIL and PASSWORD):
        print("Set CVL_EMAIL and CVL_PASSWORD environment variables first.")
        return 2
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "work_researcher", "serve", "--transport", "stdio"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()
            await call(s, "browser_open",
                       {"url": "https://www.cv-library.co.uk/login"})
            await call(s, "browser_wait", {"seconds": 3})
            d = await call(s, "browser_snapshot", {"text_chars": 400})

            els = d.get("elements") or []
            email_el = next(
                (e for e in els if e["tag"] == "input"
                 and (e.get("type") == "email"
                      or "email" in (e.get("name") or "").lower())), None)
            pw_el = next(
                (e for e in els if e.get("type") == "password"), None)
            login_btn = next(
                (e for e in els if e["tag"] == "button"
                 and (e.get("name") or "").strip().lower() in
                 ("login", "log in", "sign in")), None)
            print("form found:", bool(email_el), bool(pw_el),
                  "button:", login_btn and login_btn["n"])
            if not (email_el and pw_el):
                print("login form not found — page state:")
                print(json.dumps(d, ensure_ascii=False)[:600])
                await call(s, "browser_close")
                return 1

            await call(s, "browser_set", {"n": email_el["n"], "value": EMAIL})
            await call(s, "browser_set", {"n": pw_el["n"], "value": PASSWORD,
                                          "snapshot_after": False})
            if login_btn:
                await call(s, "browser_click", {"n": login_btn["n"]})
            else:
                await call(s, "browser_press", {"key": "Enter"})
            await call(s, "browser_wait", {"seconds": 5})

            d = await call(s, "browser_snapshot", {"text_chars": 700})
            els = d.get("elements") or []
            has_pw = any(e.get("type") == "password" for e in els)
            text = (d.get("text") or "").lower()
            url = d.get("url") or ""
            print("after login url:", url)
            print("text head:", text[:200])

            if not has_pw and "/login" not in url and "login to start" not in text:
                print("\nCV-LIBRARY LOGIN SUCCESS")
                await call(s, "browser_screenshot", {"name": "cvl-loggedin"})
                await call(s, "browser_close")
                return 0
            print("\nLOGIN NOT CONFIRMED — inspect the screenshot")
            await call(s, "browser_screenshot", {"name": "cvl-login-attempt"})
            await call(s, "browser_close")
            return 1


asyncio.run(main())
