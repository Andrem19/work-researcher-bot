"""Live test: open a Reed job, click Apply, verify browser_snapshot(modal_only=true)
shows ONLY the wizard's question + controls (vs the full page)."""
import asyncio
import json
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def call(s, name, args=None):
    r = await s.call_tool(name, args or {})
    t = [b.text for b in r.content if getattr(b, "type", "") == "text"]
    try:
        return json.loads(t[0]) if t else {}
    except (json.JSONDecodeError, IndexError):
        return {"raw": t[0] if t else None}


async def main():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "work_researcher", "serve", "--transport", "stdio"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()

            # open a Reed apprenticeship job (they trigger the 19Q wizard)
            d = await call(s, "browser_open", {
                "url": "https://www.reed.co.uk/jobs/entry-level-grad-scheme/57262727"})
            await call(s, "browser_wait", {"seconds": 3})

            # click Apply
            snap = await call(s, "browser_snapshot",
                              {"filter_text": "apply", "text_chars": 0})
            apply_els = [e for e in snap.get("elements") or []
                         if (e.get("name") or "").strip().lower()
                         .startswith("apply")]
            if not apply_els:
                print("no Apply button — page state:")
                print(json.dumps(snap, ensure_ascii=False)[:300])
                await call(s, "browser_close")
                return 1
            await call(s, "browser_click", {"n": apply_els[0]["n"]})
            await call(s, "browser_wait", {"seconds": 3})

            # THE TEST: modal_only snapshot
            modal = await call(s, "browser_snapshot", {"modal_only": True})
            els = modal.get("elements") or []
            question = modal.get("modal_question") or ""
            print("=== MODAL_ONLY SNAPSHOT ===")
            print("question:", question[:200])
            print("elements (isolated):", len(els))
            for e in els[:10]:
                print(f"  {e['n']} {e['tag']:10} {e.get('type',''):8} "
                      f"{repr((e.get('name') or '')[:50])}")

            # compare: full snapshot for contrast
            full = await call(s, "browser_snapshot", {"text_chars": 0})
            full_els = full.get("elements") or []
            print(f"\nfull snapshot elements (page behind): {len(full_els)}")
            print(f"modal isolation: {len(els)} vs {len(full_els)} "
                  f"({'GOOD' if len(els) < len(full_els) and els else 'CHECK'})")

            # try answering Q1 via browser_set (right to work = Yes radio)
            radios = [e for e in els if e.get("type") == "radio"]
            if radios:
                yes = next((e for e in radios
                            if "yes" in (e.get("name") or "").lower()), radios[0])
                ans = await call(s, "browser_set", {"n": yes["n"], "value": True})
                print(f"\nanswered Q1 (element {yes['n']}):",
                      "OK" if not ans.get("error") else ans.get("error"))
            await call(s, "browser_close")
            return 0


asyncio.run(main())
