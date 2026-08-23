import io

path = r"src\work_researcher\server.py"
h = io.open(path, encoding="utf-8").read()

# 1) duplicate-search guard at the top of _run_search
old_head = '''    async def _run_search(params: SearchParams, response_profile: str,
                          context_window: int | None,
                          requested_limit: int | None) -> dict:'''
if old_head not in h:
    # try alternate signature
    old_head = '''    async def _run_search(params: SearchParams, response_profile: str = "auto",
                          context_window: int | None = None,
                          requested_limit: int | None = None) -> dict:'''
if old_head not in h:
    # find whatever signature exists
    import re
    m = re.search(r'    async def _run_search\([^)]*\) -> dict:', h)
    if not m:
        raise SystemExit("_run_search not found")
    old_head = m.group(0)

insert_after = old_head + """
        from . import geo as geo_mod
"""
if insert_after not in h:
    # just insert guard right after the signature line
    guard = old_head + '''
        # duplicate-search guard: the same query re-run within 10 minutes
        # returns the EXISTING search_id instead of hitting the boards again
        # (weak models repeat identical searches; this saves tokens and time)
        import json as _json
        from datetime import UTC, datetime, timedelta

        async def _recent_duplicate() -> dict | None:
            try:
                aconn = await db.connect(settings.db_path)
            except Exception:
                return None
            try:
                cutoff = (datetime.now(tz=UTC) - timedelta(minutes=10)).isoformat(
                    timespec="seconds")
                cur = await aconn.execute(
                    "SELECT id, created_at, params, stats FROM searches "
                    "WHERE created_at >= ? ORDER BY created_at DESC LIMIT 8",
                    (cutoff,))
                for row in await cur.fetchall():
                    try:
                        p = _json.loads(row["params"])
                    except (TypeError, ValueError):
                        continue
                    if (p.get("query", "").lower()
                            == params.query.lower()
                            and (p.get("location") or "") == (params.location or "")):
                        return row["id"]
            finally:
                await aconn.close()
            return None

        _dup_id = await _recent_duplicate()
        if _dup_id:
            rp = _resolve_response_profile(response_profile, context_window,
                                           requested_limit)
            out = await _page_results(_dup_id, rp, offset=0)
            out["note_duplicate"] = (
                "identical query ran in the last 10 minutes — returning the "
                "existing search; page it with search_id + offset instead of "
                "re-searching")
            return out
'''
    h = h.replace(old_head, guard, 1)
    io.open(path, "w", encoding="utf-8").write(h)
    print("guard inserted after:", old_head[:80])
else:
    print("insert point already has geo import — check manually")
