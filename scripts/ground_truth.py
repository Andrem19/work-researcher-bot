"""Ground truth: do reed/indeed/cv-library homepages actually expose Sign-in
controls to our collector, and does cv-library have a Google SSO at all?"""

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
            for url in ("https://www.reed.co.uk",
                        "https://uk.indeed.com",
                        "https://www.cv-library.co.uk/account/signin"):
                d = await call(s, "browser_open", {"url": url})
                await call(s, "browser_wait", {"seconds": 3})
                d = await call(s, "browser_snapshot", {"text_chars": 8000})
                els = d.get("elements") or []
                text = (d.get("text") or "").lower()
                sign = [e for e in els if any(
                    w in (e.get("name") or "").lower()
                    for w in ("sign in", "log in", "sign up", "register"))]
                google = [e for e in els if "google" in (e.get("name") or "").lower()]
                print(f"\n{url}")
                print("  elements:", len(els), "| 'sign in' in text:", "sign in" in text)
                print("  sign-in elements:", [(e["n"], e.get("name")) for e in sign[:4]])
                print("  google elements:", [(e["n"], e.get("name")) for e in google[:4]])
            await call(s, "browser_close")


asyncio.run(main())
