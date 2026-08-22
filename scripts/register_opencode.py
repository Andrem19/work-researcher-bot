import io
import json
import re

p = r"C:\Users\andre\.config\opencode\opencode.jsonc"
h = io.open(p, encoding="utf-8").read()
if '"mcp"' not in h:
    block = (
        '  "mcp": {\n'
        '    "work-researcher": {\n'
        '      "type": "local",\n'
        '      "command": [\n'
        '        "C:\\\\Users\\\\andre\\\\miniconda3\\\\Scripts\\\\uv.exe",\n'
        '        "run", "--directory", "D:\\\\PYTHON\\\\WORK_RESEARCHER_MCP",\n'
        '        "work-researcher", "serve", "--transport", "stdio"\n'
        "      ],\n"
        '      "enabled": true\n'
        "    }\n"
        "  }\n"
        "}"
    )
    h = h.rstrip()
    assert h.endswith("}"), h[-50:]
    h = h[:-1].rstrip() + ",\n" + block + "\n"
    io.open(p, "w", encoding="utf-8").write(h)
    print("mcp block added")
else:
    print("mcp block already present")

clean = re.sub(r"//[^\n]*", "", io.open(p, encoding="utf-8").read())
d = json.loads(clean)
print("valid jsonc; mcp =", json.dumps(d.get("mcp"), indent=1))
