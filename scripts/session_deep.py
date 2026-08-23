"""Deep analysis: extract tool calls from the session regardless of format."""
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
biggest = None
biggest_len = 0
with path.open(encoding="utf-8", errors="replace") as f:
    for line in f:
        if len(line) > biggest_len:
            biggest_len = len(line)
            biggest = line

o = json.loads(biggest)
msgs = o["request"]["messages"]
print(f"messages: {len(msgs)}")

# print structure of first few messages
for i, m in enumerate(msgs[:6]):
    role = m.get("role")
    content = m.get("content")
    ctype = type(content).__name__
    preview = ""
    if isinstance(content, str):
        preview = content[:100]
    elif isinstance(content, list):
        types = [b.get("type") for b in content if isinstance(b, dict)]
        preview = f"blocks={types[:5]}"
    print(f"[{i}] role={role} content={ctype} {preview}")

# find tool_use / toolResult / functionCall blocks
print("\n=== TOOL CALLS ===")
tool_counts = {}
for i, m in enumerate(msgs):
    role = m.get("role")
    content = m.get("content")
    if isinstance(content, list):
        for b in content:
            if not isinstance(b, dict):
                continue
            btype = b.get("type", "")
            if btype in ("tool_use", "toolUse", "functionCall"):
                name = b.get("name") or b.get("functionCall", {}).get("name", "?")
                tool_counts[name] = tool_counts.get(name, 0) + 1
                args = b.get("input") or b.get("functionCall", {}).get("args", {})
                print(f"[{i}] {role}: CALL {name} args={str(args)[:120]}")
            elif btype in ("tool_result", "toolResult", "functionResponse"):
                name = b.get("name") or b.get("tool_use_id", "?")
                # get result size
                rc = b.get("content") or b.get("result", "")
                size = len(str(rc))
                print(f"[{i}] {role}: RESULT {name} size={size}")

print("\n=== TOOL COUNTS ===")
for name, count in sorted(tool_counts.items(), key=lambda x: -x[1]):
    print(f"  {count:3}x {name}")
