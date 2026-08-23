import asyncio

from work_researcher.config import load_settings
from work_researcher.cvmanager import recommend_cv
from work_researcher.persistence import connect


async def main():
    s = load_settings()
    async with connect(s.db_path) as conn:
        for title in ("Field Service Engineer Geophysical Logging",
                      "Data Analyst"):
            cur = await conn.execute(
                "SELECT * FROM jobs WHERE title LIKE ? LIMIT 1", (f"%{title.split()[0]}%",))
            rows = await cur.fetchall()
            job = None
            for r in rows:
                d = dict(r)
                if title.split()[0].lower() in (d.get("title") or "").lower():
                    job = d
                    break
            if not job:
                print(f"no stored job like {title!r}")
                continue
            recs = await recommend_cv(conn, job, limit=3)
            print(f"\n{job['title']}:")
            for rec in recs:
                print(f"  {rec['score']:.2f}  {rec['filename']}  "
                      f"match={rec['domain_match']}")


asyncio.run(main())
