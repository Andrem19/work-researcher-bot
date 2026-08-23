import io

path = r"src\work_researcher\server.py"
h = io.open(path, encoding="utf-8").read()
old = "IMPORTANT: the application form lives in THIS server"
new = ("CRITICAL: NEVER use the separate playwright MCP (mcp__playwright__*) "
       "for job pages or applications — its browser has NO logins and is a "
       "DIFFERENT context; always use this server's browser_* tools "
       "exclusively. IMPORTANT: the application form lives in THIS server")
if old in h and "CRITICAL: NEVER use the separate playwright" not in h:
    h = h.replace(old, new, 1)
    io.open(path, "w", encoding="utf-8").write(h)
    print("instruction strengthened")
else:
    print("already or not found:", "CRITICAL" in h)
