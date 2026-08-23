import io
import sys

d = io.open(r"data\session3_full.txt", encoding="utf-8", errors="replace").read()
i = d.find("=== FULL FLOW ===")
flow = d[i:]
lines = flow.split("\n")
start = int(sys.argv[1]) if len(sys.argv) > 1 else 250
end = int(sys.argv[2]) if len(sys.argv) > 2 else 400
for line in lines[start:end]:
    print(line[:200])
