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


async def main():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "work_researcher", "serve", "--transport", "stdio"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()

            # ground truth 1: login URL — redirect away = session active
            d = await call(s, "browser_open",
                           {"url": "https://www.cv-library.co.uk/account/signin"})
            await call(s, "browser_wait", {"seconds": 3})
            d = await call(s, "browser_snapshot", {"text_chars": 1000})
            els = d.get("elements") or []
            pw = [e for e in els if e.get("type") == "password"]
            print("signin url final:", d.get("url"))
            print("password inputs:", len(pw))
            print("text head:", (d.get("text") or "")[:220])

            # ground truth 2: homepage header state
            d = await call(s, "browser_open",
                           {"url": "https://www.cv-library.co.uk/"})
            await call(s, "browser_wait", {"seconds": 2})
            d = await call(s, "browser_snapshot", {"text_chars": 1000})
            els = d.get("elements") or []
            acct = [e for e in els if any(
                w in (e.get("name") or "").lower()
                for w in ("sign out", "log out", "my cv", "account", "andrew",
                          "dashboard", "profile"))]
            signin = [e for e in els if any(
                w in (e.get("name") or "").lower()
                for w in ("sign in", "log in", "register"))]
            print("\nhomepage url:", d.get("url"))
            print("account-ish elements:",
                  [(e["n"], (e.get("name") or "")[:40]) for e in acct[:6]])
            print("sign-in elements:",
                  [(e["n"], (e.get("name") or "")[:40]) for e in signin[:4]])
            print("text head:", (d.get("text") or "")[:200])

            # the agent's own tool verdict
            d = await call(s, "browser_login",
                           {"url": "https://www.cv-library.co.uk"})
            print("\nbrowser_login verdict:", json.dumps(
                {k: d.get(k) for k in ("logged_in", "needs_user", "note", "url")},
                indent=1, ensure_ascii=False))
            await call(s, "browser_close")


asyncio.run(main())
