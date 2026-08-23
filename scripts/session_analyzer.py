"""Analyze a ZCode session rollout: extract the conversation flow —
user messages, assistant texts, tool calls (name + key args + result size),
errors — to reconstruct what the agent did and where it struggled."""
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
target = sys.argv[2] if len(sys.argv) > 2 else "full"

# find the largest request line (has the most complete message history)
biggest = None
biggest_len = 0
with path.open(encoding="utf-8", errors="replace") as f:
    for line in f:
        if len(line) > biggest_len:
            biggest_len = len(line)
            biggest = line

o = json.loads(biggest)
req = o.get("request", {})
msgs = (req.get("messages")
        or req.get("body", {}).get("messages")
        or [])
if not msgs:
    print("no messages found")
    sys.exit(1)
print(f"messages: {len(msgs)} (largest request line: {biggest_len} chars)")

out = []
tool_counts = {}
errors = []
for m in msgs:
    role = m.get("role")
    content = m.get("content")
    if role == "user":
        if isinstance(content, str):
            text = content
        else:
            text = " ".join(b.get("text", "") for b in content
                            if isinstance(b, dict) and b.get("type") == "text")
        if text.strip() and not text.startswith("<task-notification>") \
                and "tool_result" not in str(content)[:50]:
            out.append(("USER", text[:400]))
    elif role == "assistant":
        if isinstance(content, list):
            for b in content:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text" and b.get("text", "").strip():
                    out.append(("ASSISTANT", b["text"][:300]))
                elif b.get("type") == "tool_use":
                    name = b.get("name", "?")
                    tool_counts[name] = tool_counts.get(name, 0) + 1
                    args = b.get("input", {})
                    short = ""
                    if name == "mcp__work-researcher__search_jobs":
                        short = f"q={args.get('query') or args.get('profile')} loc={args.get('location')}"
                    elif name == "mcp__work-researcher__get_job":
                        short = f"ids={args.get('job_ids')}"
                    elif name == "mcp__work-researcher__fetch_job_description":
                        short = f"id={args.get('job_id')}"
                    elif name.startswith("mcp__work-researcher__browser"):
                        short = str(args)[:80]
                    elif name == "mcp__work-researcher__start_application":
                        short = f"job={args.get('job_id')}"
                    else:
                        short = str(args)[:60]
                    out.append(("TOOL", f"{name}({short})"))

print("\n=== TOOL USAGE ===")
for name, count in sorted(tool_counts.items(), key=lambda x: -x[1]):
    print(f"  {count:3}x {name}")

print("\n=== CONVERSATION FLOW ===")
for role, text in out:
    print(f"[{role:9}] {text[:200]}")
