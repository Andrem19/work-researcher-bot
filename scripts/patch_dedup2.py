import io

path = r"src\work_researcher\server.py"
h = io.open(path, encoding="utf-8").read()

sig = "    async def _run_search(params: SearchParams, response_policy: dict[str, Any]) -> dict:\n"
assert sig in h, "signature not found"

guard = sig + '''        # duplicate-search guard: the same query re-run within 10 minutes
        # returns the EXISTING search_id instead of hitting the boards again
        # (weak models repeat identical searches; this saves tokens and time)
        async def _recent_duplicate() -> str | None:
            from datetime import UTC, datetime, timedelta

            try:
                aconn = await db.connect(settings.db_path)
            except Exception:  # noqa: BLE001
                return None
            try:
                cutoff = (datetime.now(tz=UTC)
                          - timedelta(minutes=10)).isoformat(timespec="seconds")
                cur = await aconn.execute(
                    "SELECT id, params FROM searches "
                    "WHERE created_at >= ? ORDER BY created_at DESC LIMIT 8",
                    (cutoff,))
                for row in await cur.fetchall():
                    try:
                        p = json.loads(row["params"])
                    except (TypeError, ValueError):
                        continue
                    if (p.get("query", "").lower() == params.query.lower()
                            and (p.get("location") or "") == (params.location or "")):
                        return row["id"]
            finally:
                await aconn.close()
            return None

        _dup_id = await _recent_duplicate()
        if _dup_id:
            out = await _page_results(_dup_id, response_policy, offset=0)
            out["note_duplicate"] = (
                "identical query ran in the last 10 minutes — returning the "
                "existing search; PAGE it with search_id + offset instead of "
                "re-searching")
            return out
'''

h = h.replace(sig, guard, 1)
io.open(path, "w", encoding="utf-8").write(h)
print("duplicate-search guard inserted")
