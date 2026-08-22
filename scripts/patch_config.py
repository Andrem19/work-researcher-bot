import io
import re

p = "config.toml"
h = io.open(p, encoding="utf-8").read()

h = re.sub(r'app_id = ""[^\n]*', 'app_id = ""', h, count=1)
h = re.sub(r'app_key = ""[^\n]*',
           'app_key = "208deb64cc4764ea09339c18dda752ed"', h, count=1)
h = re.sub(r'full_name = ""[^\n]*', 'full_name = "Andrew"', h, count=1)
h = re.sub(r'phone = ""[^\n]*', 'phone = "+447838228012"', h, count=1)
io.open(p, "w", encoding="utf-8").write(h)
for line in h.splitlines():
    if any(k in line for k in ("app_id", "app_key", "full_name", "phone")):
        print(line)
