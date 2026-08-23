import io

path = r"src\work_researcher\server.py"
h = io.open(path, encoding="utf-8").read()

anchor = "REQUIREMENTS CHECK: jobs with hard requirements"
addition = (
    "TOKEN DISCIPLINE: never re-run the same search_jobs query twice — the "
    "tool returns note_duplicate with the existing search_id; PAGE it via "
    "search_id+offset instead. Never query the SQLite DB via Bash — use "
    "list_stored_jobs (filter stored jobs by company/title/location/source). "
    "Batch fetch_job_description(job_ids=[...]) up to 10 at once instead of "
    "one-by-one calls. "
)
if addition not in h and anchor in h:
    h = h.replace(anchor, addition + anchor, 1)
    io.open(path, "w", encoding="utf-8").write(h)
    print("instructions updated")
else:
    print("anchor:", anchor in h, "| already:", addition in h)
