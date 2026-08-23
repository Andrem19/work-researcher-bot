import io

path = r"src\work_researcher\server.py"
h = io.open(path, encoding="utf-8").read()

old = '''        async def _recent_duplicate() -> str | None:
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
            return None'''

new = '''        async def _recent_duplicate() -> str | None:
            from datetime import UTC, datetime, timedelta

            try:
                async with db.connect(settings.db_path) as aconn:
                    cutoff = (datetime.now(tz=UTC) - timedelta(minutes=10)) \\
                        .isoformat(timespec="seconds")
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
                                and (p.get("location") or "")
                                == (params.location or "")):
                            return row["id"]
            except Exception:  # noqa: BLE001 - the guard must never break search
                return None
            return None'''

if old in h:
    h = h.replace(old, new, 1)
    io.open(path, "w", encoding="utf-8").write(h)
    print("guard connection fixed")
else:
    print("PATTERN NOT FOUND")
