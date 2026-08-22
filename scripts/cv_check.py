import asyncio
import json

from work_researcher.config import load_settings
from work_researcher.cvmanager import recommend_cv
from work_researcher.persistence import connect


async def main():
    s = load_settings()
    async with connect(s.db_path) as conn:
        cur = await conn.execute(
            "SELECT filename, tags, language, name_guess, length(full_text) AS n, "
            "substr(text_preview,1,60) AS prev FROM cvs ORDER BY filename"
        )
        print("== CV index ==")
        for r in await cur.fetchall():
            print(f"{r['filename']:42} tags={r['tags']:40} lang={r['language']} "
                  f"chars={r['n']:6} | {r['prev']}")
        # recommendation check for two live jobs
        for title in ("Data Analyst", "Engineering Geologist"):
            cur = await conn.execute(
                "SELECT * FROM jobs WHERE title LIKE ? AND company IS NOT NULL "
                "LIMIT 1", (f"%{title}%",))
            job = await cur.fetchone()
            if not job:
                print(f"\nno stored job for {title!r}")
                continue
            recs = await recommend_cv(conn, dict(job), limit=3)
            print(f"\n== best CVs for '{job['title']}' ({job['company']}) ==")
            for rec in recs:
                print(f"  {rec['score']:.2f}  {rec['filename']}  {rec['tags']}")


asyncio.run(main())
