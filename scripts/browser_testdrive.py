"""BROWSER TEST DRIVE over MCP stdio — real Edge (headed), NO submissions:

browser_login (totaljobs) → snapshot/filter/form → reed job page → tabs →
screenshot → close. browser_login may end with needs_user=true (Google
password/2FA in a fresh profile) — that is the DESIGNED outcome, not a bug."""

from __future__ import annotations

import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = [sys.executable, "-m", "work_researcher", "serve", "--transport", "stdio"]
PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


async def call(session, name, args=None):
    result = await session.call_tool(name, args or {})
    texts = [b.text for b in result.content if getattr(b, "type", "") == "text"]
    try:
        return json.loads(texts[0]) if texts else {}
    except (json.JSONDecodeError, IndexError):
        return {"raw": texts[0] if texts else None, "is_error": result.is_error}


async def main() -> int:
    params = StdioServerParameters(command=SERVER[0], args=SERVER[1:])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1) login flow on Totaljobs
            login = await call(session, "browser_login",
                               {"url": "https://www.totaljobs.com"})
            check("browser_login runs and reports a definite state",
                  "logged_in" in login,
                  f"logged_in={login.get('logged_in')} needs_user={login.get('needs_user')} "
                  f"note={str(login.get('note'))[:80]}")

            # 2) Reed job page: search → open → filter/form/text
            search = await call(session, "search_jobs",
                                {"query": "Data Analyst", "limit_per_source": 5,
                                 "sources": ["reed"]})
            rows = [r for r in search.get("results", []) if r.get("url")]
            if not rows:
                check("reed row for browser test", False, "no results")
                return 1
            opened = await call(session, "browser_open", {"url": rows[0]["url"]})
            check("browser_open(reed job) 200",
                  opened.get("http_status") == 200, str(opened.get("title"))[:60])
            # apply-filter belongs on a JOB page (that's where agents use it)
            snap = await call(session, "browser_snapshot",
                              {"filter_text": "apply", "text_chars": 0})
            check("snapshot(filter_text=apply) finds controls on job page",
                  len(snap.get("elements") or []) > 0,
                  f"{len(snap.get('elements') or [])} matches")
            text = await call(session, "browser_snapshot", {"text_chars": 4000})
            check("snapshot reading mode returns text",
                  len(text.get("text") or "") > 500,
                  f"{len(text.get('text') or '')} chars")
            form = await call(session, "browser_form")
            check("browser_form returns a structure",
                  isinstance(form.get("fields"), list))

            # 4) tabs
            tabs = await call(session, "browser_tabs", {"action": "list"})
            check("browser_tabs lists open tabs", len(tabs.get("tabs", [])) >= 1,
                  f"{len(tabs.get('tabs', []))}")

            # 5) screenshot + close
            shot = await call(session, "browser_screenshot", {"name": "testdrive"})
            check("screenshot saved", bool(shot.get("screenshot")))
            closed = await call(session, "browser_close")
            check("browser_close", closed.get("closed") is True)

    print("\n================ BROWSER TEST DRIVE ================")
    print(f"PASS: {len(PASS)}  FAIL: {len(FAIL)}")
    if FAIL:
        print("FAILED:", FAIL)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
