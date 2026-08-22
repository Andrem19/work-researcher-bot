"""Google-auth verification tour: browser_login on several UK job boards.

After the user typed the Google password once in the automation profile, the
Google session should carry every 'Continue with Google' flow automatically.
Reports the final state per board."""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = [sys.executable, "-m", "work_researcher", "serve", "--transport", "stdio"]

BOARDS = [
    "https://www.totaljobs.com",
    "https://www.reed.co.uk",
    "https://www.cv-library.co.uk",
    "https://uk.indeed.com",
]


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
            for board in BOARDS:
                r = await call(s, "browser_login", {"url": board})
                url = (r.get("url") or "")[:70]
                print(f"{board:35} logged_in={r.get('logged_in')} "
                      f"needs_user={r.get('needs_user')}")
                print(f"{'':35} url={url}")
                print(f"{'':35} note={str(r.get('note') or r.get('error'))[:100]}")
                print()
            await call(s, "browser_close")
    return 0


asyncio.run(main())
