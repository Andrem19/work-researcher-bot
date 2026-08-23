"""Full analysis: response.text + response.toolCalls per line, plus
request.messages tool results — reconstruct the agent's complete behavior."""
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
tool_counts = {}
events = []

with path.open(encoding="utf-8", errors="replace") as f:
    lines = f.readlines()

for idx, line in enumerate(lines):
    try:
        o = json.loads(line)
    except json.JSONDecodeError:
        continue
    resp = o.get("response", {})
    if not isinstance(resp, dict):
        continue

    # tool calls
    for tc in resp.get("toolCalls", []) or []:
        name = tc.get("toolName") or tc.get("name", "?")
        args = tc.get("args") or tc.get("input", {})
        tool_counts[name] = tool_counts.get(name, 0) + 1
        args_short = ""
        if name.endswith("search_jobs"):
            args_short = f"q={args.get('query') or args.get('profile')} " \
                         f"loc={args.get('location')} lim={args.get('limit_per_source')}"
        elif name.endswith("get_job"):
            args_short = f"{args.get('job_ids')}"
        elif name.endswith("fetch_job_description"):
            args_short = f"{args.get('job_id')}"
        elif name.endswith("start_application"):
            args_short = f"job={args.get('job_id')}"
        elif "browser" in name:
            args_short = str(args)[:70]
        else:
            args_short = str(args)[:70]
        events.append(("TOOL", name.replace("mcp__work-researcher__", "wr."),
                       args_short))

    # text
    text = resp.get("text", "")
    if text:
        # strip thinking tags
        clean = text
        for tag in ("<analysis>", "</analysis>", "<thinking>", "</thinking>"):
            clean = clean.replace(tag, "")
        clean = clean.strip()
        if clean:
            events.append(("TEXT", "", clean[:350]))

    # usage
    usage = resp.get("usage", {})
    if usage.get("totalTokens"):
        events.append(("USAGE", "", f"in={usage.get('inputTokens')} "
                                     f"out={usage.get('outputTokens')}"))

print(f"events: {len(events)}\n")
print("=== TOOL COUNTS ===")
for name, count in sorted(tool_counts.items(), key=lambda x: -x[1]):
    print(f"  {count:3}x {name}")

print("\n=== FULL FLOW ===")
for kind, name, text in events:
    if kind == "TOOL":
        print(f"  → {name}({text})")
    elif kind == "USAGE":
        print(f"  [tokens: {text}]")
    else:
        # first line only for brevity
        first = text.split("\n")[0][:200]
        print(f"  💬 {first}")
