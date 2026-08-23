import io

path = r"src\work_researcher\server.py"
h = io.open(path, encoding="utf-8").read()

# 1) None/empty guard
old1 = '''        results = []
        jobs = []
        async with db.connect(settings.db_path) as conn:
            for jid in job_ids[:10]:'''
new1 = '''        if not job_ids:
            return {"error": "job_ids list is empty"}
        job_ids = [j for j in job_ids if j][:10]
        if not job_ids:
            return {"error": "job_ids contained no valid ids"}
        results = []
        jobs = []
        async with db.connect(settings.db_path) as conn:
            for jid in job_ids:'''
if old1 in h:
    h = h.replace(old1, new1, 1)
    print("guard added")
else:
    print("guard: pattern not found")

# 2) per-job timeout with partial results (batch cap lowered from 10 to 6)
old2 = '''            try:
                await sess.open(url)
                await sess._active().wait_for_timeout(2500)'''
new2 = '''            try:
                await asyncio.wait_for(sess.open(url), timeout=25)
                await sess._active().wait_for_timeout(1500)'''
if old2 in h:
    h = h.replace(old2, new2, 1)
    print("per-job timeout added")
else:
    print("timeout: pattern not found")

# 3) timeout error also produces partial result, not skip
old3 = '''            except BrowserError as exc:
                results.append({"job_id": jid, "error": str(exc)})
                continue'''
new3 = '''            except (BrowserError, asyncio.TimeoutError, Exception) as exc:
                results.append({"job_id": jid,
                                "error": f"{type(exc).__name__}: {str(exc)[:120]}"})
                continue'''
if old3 in h:
    h = h.replace(old3, new3, 1)
    print("partial-results on error")
else:
    print("except: pattern not found")

io.open(path, "w", encoding="utf-8").write(h)
print("done")
