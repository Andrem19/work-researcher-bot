import io

path = "config.toml"
h = io.open(path, encoding="utf-8").read()
add = (
    'date_of_birth = ""\n'
    'nationality = "British"\n'
    'right_to_work_docs = "UK birth certificate"\n'
    'uk_residence_years = "10+"\n'
    'age_group = "35-39"\n'
)
anchor = 'phone = "+447838228012"'
if anchor in h and "date_of_birth" not in h:
    h = h.replace(anchor, anchor + "\n" + add.rstrip(), 1)
    io.open(path, "w", encoding="utf-8").write(h)
    print("config.toml updated with wizard fields")
else:
    print("anchor:", anchor in h, "| present:", "date_of_birth" in h)
