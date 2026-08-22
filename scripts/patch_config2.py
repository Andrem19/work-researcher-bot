import io
import re

p = "config.toml"
h = io.open(p, encoding="utf-8").read()
h = re.sub(r'app_id = ""[^\n]*', 'app_id = "41d7a581"', h, count=1)
io.open(p, "w", encoding="utf-8").write(h)
for line in h.splitlines():
    if "app_id" in line or "app_key" in line:
        print(line)
