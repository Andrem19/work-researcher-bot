"""Inspect the raw JSONL structure: keys, response shape, sample values."""
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
with path.open(encoding="utf-8", errors="replace") as f:
    lines = f.readlines()

print(f"total lines: {len(lines)}")
# sample a mid-file line
for idx in [0, len(lines)//2, -1]:
    o = json.loads(lines[idx])
    print(f"\n=== line {idx} ===")
    print("top keys:", list(o.keys()))
    if "response" in o:
        resp = o["response"]
        print("response keys:", list(resp.keys()) if isinstance(resp, dict) else type(resp))
        if isinstance(resp, dict):
            for k, v in resp.items():
                if isinstance(v, dict):
                    print(f"  {k}: dict keys={list(v.keys())[:8]}")
                elif isinstance(v, list):
                    print(f"  {k}: list len={len(v)}")
                    if v and isinstance(v[0], dict):
                        print(f"    [0] keys={list(v[0].keys())[:8]}")
                else:
                    print(f"  {k}: {str(v)[:80]}")
