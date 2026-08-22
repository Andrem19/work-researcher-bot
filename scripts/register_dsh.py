import io

BLOCK = """
- id: mcp-work-researcher
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: work-researcher
    transport: stdio
    command: "C:\\\\Users\\\\andre\\\\miniconda3\\\\Scripts\\\\uv.exe"
    args:
      - run
      - --directory
      - "D:\\\\PYTHON\\\\WORK_RESEARCHER_MCP"
      - work-researcher
      - serve
      - --transport
      - stdio
    toolCallTimeoutMs: 180000
"""

for profile in ("headless", "web"):
    p = rf"C:\Users\andre\.dsh\profiles\{profile}\cordis.patch.yml"
    h = io.open(p, encoding="utf-8").read()
    if "mcp-work-researcher" in h:
        print(profile, "already registered")
        continue
    if not h.endswith("\n"):
        h += "\n"
    h += BLOCK
    io.open(p, "w", encoding="utf-8").write(h)
    print(profile, "patched")
