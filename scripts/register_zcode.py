import json

p = r"C:\Users\andre\.zcode\cli\config.json"
d = json.load(open(p, encoding="utf-8"))
d.setdefault("mcp", {}).setdefault("servers", {})["work-researcher"] = {
    "type": "stdio",
    "command": r"C:\Users\andre\miniconda3\Scripts\uv.exe",
    "args": ["run", "--directory", r"D:\PYTHON\WORK_RESEARCHER_MCP",
             "work-researcher", "serve", "--transport", "stdio"],
}
json.dump(d, open(p, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("zcode servers:", list(d["mcp"]["servers"]))
