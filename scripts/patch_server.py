import io
import re

path = r"src\work_researcher\server.py"
h = io.open(path, encoding="utf-8").read()

m = re.search(
    r'    @mcp\.tool\(\)\n    async def fetch_job_description\(job_id: str\) -> dict:.*?(?=    @mcp\.tool\(\))',
    h, re.S)
assert m, "old fetch block not found"
old_block = m.group(0)

new_block = '''    @mcp.tool()
    async def fetch_job_description(job_ids: list[str]) -> dict:
        """Fetch FULL job descriptions by opening pages in the browser.
        Accepts 1-10 job_ids (BATCH - prefer batching to save round-trips).
        Use for jobs where the parser returned null/short descriptions
        (common on Totaljobs/Reed). Stores descriptions back and re-runs the
        requirements check against your CVs. Also detects closed vacancies
        ("no longer accepting applications")."""
        from . import requirements as req_mod
        from .browser import BrowserError, get_session

        results = []
        jobs = []
        async with db.connect(settings.db_path) as conn:
            for jid in job_ids[:10]:
                job = await db.get_job(conn, jid)
                if not job:
                    results.append({"job_id": jid, "error": "unknown"})
                else:
                    jobs.append(job)
        if not jobs:
            return {"results": results}
        sess = get_session(settings)
        for job in jobs:
            jid = job["id"]
            url = job.get("apply_url") or job.get("url")
            if not url:
                results.append({"job_id": jid, "error": "no URL"})
                continue
            try:
                await sess.open(url)
                await sess._active().wait_for_timeout(2500)
                result = await sess.evaluate(
                    "() => (document.body.innerText || '').replace(/\\\\s+/g, ' ')")
                full_text = (result.get("result") or "")
                desc_start = full_text.find("Job description")
                if desc_start == -1:
                    desc_start = full_text.find("About the role")
                if desc_start == -1:
                    desc_start = 500
                desc_end = full_text.rfind("Apply")
                if desc_end == -1 or desc_end <= desc_start:
                    desc_end = len(full_text)
                description = full_text[desc_start:desc_end].strip()[:8000]
                closed = any(marker in full_text.lower() for marker in
                             ("no longer accepting", "can no longer apply",
                              "vacancy has been closed", "position has been filled",
                              "closing date has passed"))
            except BrowserError as exc:
                results.append({"job_id": jid, "error": str(exc)})
                continue

            async with db.connect(settings.db_path) as conn:
                await conn.execute(
                    "UPDATE jobs SET description=? WHERE id=?", (description, jid))
                cur = await conn.execute(
                    "SELECT full_text FROM cvs ORDER BY length(full_text) DESC LIMIT 3")
                cv_rows = await cur.fetchall()
                cv_text = "\\n".join((r["full_text"] or "") for r in cv_rows)
                reqs = req_mod.extract_requirements(description)
                match = req_mod.match_requirements(reqs, cv_text)
                cur2 = await conn.execute("SELECT extra FROM jobs WHERE id=?", (jid,))
                row = await cur2.fetchone()
                extra = {}
                try:
                    extra = json.loads(row["extra"] or "{}")
                except (TypeError, ValueError):
                    pass
                extra["requirements_status"] = match["status"]
                extra["requirements_unmet"] = [r["value"] for r in match["unmet"]]
                await conn.execute("UPDATE jobs SET extra=? WHERE id=?",
                                   (json.dumps(extra, ensure_ascii=False), jid))
                await conn.commit()
            results.append({
                "job_id": jid,
                "description_length": len(description),
                "description_preview": description[:400],
                "requirements_status": match["status"],
                "requirements_unmet": [r["value"] for r in match["unmet"]],
                "vacancy_closed": closed or None,
            })
        return {"results": results}

    @mcp.tool()
    async def list_stored_jobs(
        query: str | None = None,
        company: str | None = None,
        location: str | None = None,
        source: str | None = None,
        days_old: int = 7,
        limit: int = 20,
    ) -> dict:
        """Search the LOCAL job database by criteria (no board calls). Use
        INSTEAD of Bash/sqlite: find all jobs from a company, filter by title
        keyword, location, source board, or freshness. Returns job_ids +
        titles + requirements status - then get_job / fetch_job_description
        for detail."""
        async with db.connect(settings.db_path) as conn:
            sql = ("SELECT id, title, company, location_text, salary_raw, "
                   "posted_at, source, extra, description FROM jobs "
                   "WHERE last_seen >= datetime('now', ?)")
            args: list = [f"-{days_old} days"]
            if query:
                sql += " AND (title LIKE ? OR description LIKE ?)"
                args += [f"%{query}%", f"%{query}%"]
            if company:
                sql += " AND company LIKE ?"
                args.append(f"%{company}%")
            if location:
                sql += " AND location_text LIKE ?"
                args.append(f"%{location}%")
            if source:
                sql += " AND source = ?"
                args.append(source)
            sql += " ORDER BY posted_at DESC LIMIT ?"
            args.append(limit)
            cur = await conn.execute(sql, args)
            rows = []
            for r in await cur.fetchall():
                extra = {}
                try:
                    extra = json.loads(r["extra"] or "{}")
                except (TypeError, ValueError):
                    pass
                rows.append({
                    "job_id": r["id"], "title": r["title"],
                    "company": r["company"], "location": r["location_text"],
                    "salary": r["salary_raw"], "posted_at": r["posted_at"],
                    "source": r["source"],
                    "requirements_status": extra.get("requirements_status"),
                    "requirements_unmet": extra.get("requirements_unmet"),
                    "has_description": bool(r["description"]
                                            and len(r["description"]) > 200),
                })
            return {"jobs": rows, "count": len(rows),
                    "note": "get_job for full records; fetch_job_description "
                            "to enrich missing ones"}

    @mcp.tool()
'''

h = h.replace(old_block, new_block)
io.open(path, "w", encoding="utf-8").write(h)
print("replaced fetch_job_description + added list_stored_jobs")
print("old len:", len(old_block), "new len:", len(new_block))
