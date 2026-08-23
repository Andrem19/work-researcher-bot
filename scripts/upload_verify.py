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
            d = await call(s, "browser_open", {
                "url": "https://www.totaljobs.com/job/data-analyst/experis-job107876163"})
            await call(s, "browser_wait", {"seconds": 2})
            snap = await call(s, "browser_snapshot",
                              {"filter_text": "continue", "text_chars": 0})
            els = snap.get("elements") or []
            if not els:
                print("no continue button")
                await call(s, "browser_close")
                return 1
            await call(s, "browser_click", {"n": els[0]["n"]})
            await call(s, "browser_wait", {"seconds": 4})

            # find the file input in the snapshot
            snap = await call(s, "browser_snapshot", {"text_chars": 300})
            inputs = [e for e in snap.get("elements") or []
                      if e.get("type") == "file"]
            print("file inputs:", [(e["n"], e.get("name")) for e in inputs])
            if not inputs:
                await call(s, "browser_close")
                return 1
            up = await call(s, "browser_upload", {
                "n": inputs[0]["n"],
                "file_path": r"D:\PYTHON\WORK_RESEARCHER_MCP\CV_collection\Test_Cover_Letter.docx"})
            print("upload err:", up.get("error"))
            await call(s, "browser_wait", {"seconds": 3})
            after = await call(s, "browser_snapshot", {"text_chars": 3000})
            text = after.get("text") or ""
            found = "Test_Cover_Letter" in text
            print("filename visible in UI:", found)
            print("text excerpt:", text[:400].replace("\n", " "))
            await call(s, "browser_screenshot", {"name": "upload-verify"})
            await call(s, "browser_close")
            print("VERDICT:", "UPLOAD WORKS" if found else "UPLOAD NOT SHOWN — check screenshot")


asyncio.run(main())
