import json
import sqlite3

db = sqlite3.connect(r"D:\PYTHON\WORK_RESEARCHER_MCP\data\work_researcher.db")
db.row_factory = sqlite3.Row
rows = db.execute(
    "SELECT id, created_at, params FROM searches "
    "ORDER BY created_at DESC LIMIT 4").fetchall()
for r in rows:
    p = json.loads(r["params"])
    print(f"id={r['id']} created={r['created_at']}")
    print(f"  query={p.get('query')!r} location={p.get('location')!r}")
