"""Call _run_search's duplicate logic manually to see what happens."""
import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta

sys.path.insert(0, "src")
from work_researcher.config import load_settings          # noqa: E402
from work_researcher.domain import SearchParams           # noqa: E402
from work_researcher.persistence import connect           # noqa: E402


async def main():
    s = load_settings()
    params = SearchParams(query="lab technician", location="UK")
    async with connect(s.db_path) as conn:
        cutoff = (datetime.now(tz=UTC)
                  - timedelta(minutes=10)).isoformat(timespec="seconds")
        print("cutoff:", cutoff, "| params.query:", repr(params.query),
              "| params.location:", repr(params.location))
        cur = await conn.execute(
            "SELECT id, params FROM searches "
            "WHERE created_at >= ? ORDER BY created_at DESC LIMIT 8",
            (cutoff,))
        for row in await cur.fetchall():
            p = json.loads(row["params"])
            q_match = p.get("query", "").lower() == params.query.lower()
            l_match = (p.get("location") or "") == (params.location or "")
            print(f"  {row['id']}: stored_q={p.get('query')!r} "
                  f"stored_loc={p.get('location')!r} "
                  f"q_match={q_match} l_match={l_match} "
                  f"-> {'DUPLICATE' if q_match and l_match else 'no'}")


asyncio.run(main())
