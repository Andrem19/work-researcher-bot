"""Regression test for the failed-application problems:
1) make_cover_letter produces a >8KB DOCX;
2) browser_upload attaches a file to Totaljobs' HIDDEN supporting-files
   input on a real apply form (NO submission at the end)."""

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

            # 1) cover letter factory
            cl = await call(s, "make_cover_letter", {
                "name": "Test_Cover_Letter",
                "text": "Andrew Remniow\n\nDear Hiring Manager,\n\n"
                        "I am applying for this position.\n\n"
                        "Kind regards,\nAndrew Remniow",
            })
            print("cover letter:", cl)
            cl_ok = cl.get("size_bytes", 0) > 8192

            # 2) find a live totaljobs job
            search = await call(s, "search_jobs", {
                "query": "Data Analyst", "limit_per_source": 5,
                "sources": ["totaljobs"]})
            rows = [r for r in search.get("results", []) if r.get("url")]
            if not rows:
                print("no totaljobs rows")
                return 1
            url = rows[0]["url"]
            print("job:", rows[0]["title"], "|", url)

            opened = await call(s, "browser_open", {"url": url})
            print("opened:", opened.get("title"))

            # find and click Apply (SPA renders late — retry)
            apply_els = []
            for _attempt in range(4):
                await call(s, "browser_wait", {"seconds": 2})
                snap = await call(s, "browser_snapshot",
                                  {"filter_text": "appl", "text_chars": 0})
                apply_els = [e for e in snap.get("elements") or []
                             if (e.get("name") or "").strip().lower()
                             .startswith(("apply", "continue application"))][:3]
                if apply_els:
                    break
            if not apply_els:
                print("no Apply control after retries")
                await call(s, "browser_screenshot", {"name": "no-apply"})
                await call(s, "browser_close")
                return 1
            print("apply candidates:",
                  [(e["n"], e.get("name")) for e in apply_els])
            clicked = await call(s, "browser_click", {"n": apply_els[0]["n"]})
            print("after Apply url:", clicked.get("url"))

            # wait for the form to appear
            await call(s, "browser_wait", {"seconds": 4})
            form = await call(s, "browser_snapshot", {"text_chars": 300})
            els = form.get("elements") or []

            # find any file input in the snapshot; if hidden inputs are not
            # tagged, expose them via eval and use browser_upload fallback
            file_inputs = [e for e in els if e.get("type") == "file"]
            print("file inputs in snapshot:", len(file_inputs))
            probe = await call(s, "browser_eval", {"js":
                "() => Array.from(document.querySelectorAll('input[type=file]'))"
                ".map(i => ({n: i.getAttribute('data-wr-n'), accept: i.accept,"
                " multiple: i.multiple}))"})
            print("DOM file inputs:", probe.get("result"))

            if file_inputs:
                up = await call(s, "browser_upload", {
                    "n": file_inputs[0]["n"], "file_path": cl.get("path")})
                up_err = up.get("error")
                # verify the input actually holds a file now
                check = await call(s, "browser_eval", {"js":
                    "() => Array.from(document.querySelectorAll('input[type=file]'))"
                    ".map(i => i.files.length)"})
                print("upload error:", up_err)
                print("files on inputs:", check.get("result"))
                attached = any(check.get("result") or []) and not up_err
            else:
                print("no file input visible — see DOM probe above")
                attached = False

            await call(s, "browser_screenshot", {"name": "upload-test"})
            await call(s, "browser_close")
            print("\nVERDICT:",
                  "PASS" if (cl_ok and attached) else
                  f"PARTIAL (cover_letter={cl_ok}, upload={attached})")
            return 0 if (cl_ok and attached) else 1


asyncio.run(main())
