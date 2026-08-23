"""Extract the full conversation flow from ALL lines of the JSONL —
both requests (user messages) and responses (assistant text + tool calls)."""
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])

tool_counts = {}
flow = []  # (kind, text)

with path.open(encoding="utf-8", errors="replace") as f:
    for line_no, line in enumerate(f, 1):
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        req = o.get("request", {})
        resp = o.get("response", {})

        # response body: look for assistant content / tool calls
        rbody = resp.get("body") if isinstance(resp, dict) else {}
        if rbody is None:
            rbody = {}
        # streaming responses may nest differently
        choices = rbody.get("choices", []) if isinstance(rbody, dict) else []
        for ch in choices:
            msg = ch.get("message", {}) or ch.get("delta", {}) or {}
            # tool_calls (OpenAI format)
            for tc in msg.get("tool_calls", []) or []:
                fn = tc.get("function", {})
                name = fn.get("name", "?")
                args = fn.get("arguments", "")
                tool_counts[name] = tool_counts.get(name, 0) + 1
                flow.append(("TOOL", f"{name}({str(args)[:100]})"))
            text = msg.get("content")
            if isinstance(text, str) and text.strip():
                flow.append(("ASSISTANT", text[:250]))
            elif isinstance(text, list):
                for b in text:
                    if isinstance(b, dict) and b.get("type") == "text":
                        flow.append(("ASSISTANT", b.get("text", "")[:250]))

        # non-streaming: content at top level
        content = rbody.get("content") if isinstance(rbody, dict) else None
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict):
                    if b.get("type") == "text" and b.get("text", "").strip():
                        flow.append(("ASSISTANT", b["text"][:250]))
                    elif b.get("type") == "tool_use":
                        name = b.get("name", "?")
                        tool_counts[name] = tool_counts.get(name, 0) + 1
                        flow.append(("TOOL", f"{name}({str(b.get('input',{}))[:100]})"))

        # tool results come back as user messages in the NEXT request
        # extract from request messages
        for m in req.get("messages", []):
            if m.get("role") == "user":
                c = m.get("content")
                text = c if isinstance(c, str) else ""
                if isinstance(c, list):
                    for b in c:
                        if isinstance(b, dict) and b.get("type") == "tool_result":
                            rc = b.get("content", "")
                            flow.append(("RESULT", f"size={len(str(rc))}"))

print(f"flow events: {len(flow)}")
print("\n=== TOOL COUNTS ===")
for name, count in sorted(tool_counts.items(), key=lambda x: -x[1]):
    print(f"  {count:3}x {name}")

print("\n=== FLOW (first 80 events) ===")
for kind, text in flow[:80]:
    print(f"[{kind:9}] {text[:180]}")
