"""Debug the dedup guard directly."""
import asyncio
import json
import sqlite3

from work_researcher.config import load_settings
from work_researcher.persistence import connect


async def main():
    s = load_settings()
    async with connect(s.db_path) as conn:
        from datetime import UTC, datetime, timedelta

        cutoff = (datetime.now(tz=UTC)
                  - timedelta(minutes=10)).isoformat(timespec="seconds")
        print("cutoff:", cutoff)
        cur = await conn.execute(
            "SELECT id, created_at, params FROM searches "
            "WHERE created_at >= ? ORDER BY created_at DESC LIMIT 8",
            (cutoff,))
        rows = await cur.fetchall()
        print("rows found:", len(rows))
        for row in rows:
            p = json.loads(row["params"])
            print(f"  {row['id']} q={p.get('query')} loc={p.get('location')} "
                  f"match={'lab technician' == p.get('query', '').lower()}")


asyncio.run(main())
