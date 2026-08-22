"""Verify Totaljobs login state honestly + apply-filter on a real job page."""

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
        async with ClientSession(read, write) as session:
            await session.initialize()
            opened = await call(session, "browser_open",
                                {"url": "https://www.totaljobs.com/"})
            text = (opened.get("text") or "").lower()
            els = opened.get("elements") or []
            sign_els = [e for e in els
                        if "sign" in (e.get("name") or "").lower()
                        or "log in" in (e.get("name") or "").lower()]
            account_els = [e for e in els
                           if any(w in (e.get("name") or "").lower()
                                  for w in ("my ", "profile", "account", "logout",
                                            "sign out"))]
            print("page title:", opened.get("title"))
            print("'sign in' in page text:", "sign in" in text)
            print("sign-in elements:", [(e["n"], e.get("name")) for e in sign_els[:5]])
            print("account elements:", [(e["n"], e.get("name")) for e in account_els[:5]])
            print("text excerpt:", text[:200])
            await call(session, "browser_close")
    return 0


asyncio.run(main())
