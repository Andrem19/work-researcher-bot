import io

path = r"src\work_researcher\server.py"
h = io.open(path, encoding="utf-8").read()
needle = "    @mcp.tool()\n    @mcp.tool()\n"
count = h.count(needle)
print("double decorators:", count)
if count:
    h = h.replace(needle, "    @mcp.tool()\n")
    io.open(path, "w", encoding="utf-8").write(h)
    print("fixed")
else:
    print("no doubles found")
