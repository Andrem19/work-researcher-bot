import io

path = "config.toml"
h = io.open(path, encoding="utf-8").read()
add = (
    'gender = "Male"\n'
    'ethnicity = "White"\n'
    'still_in_education = false\n'
    'earliest_start_date = ""\n'
    'highest_qualification = "Level 6 (BSc degree, NARIC confirmed)"\n'
    'past_apprenticeship = false\n'
    'owns_car = true\n'
)
anchor = 'age_group = "35-39"'
if anchor in h and 'gender = ' not in h:
    h = h.replace(anchor, anchor + "\n" + add.rstrip(), 1)
    io.open(path, "w", encoding="utf-8").write(h)
    print("config.toml updated")
else:
    print("anchor:", anchor in h, "| gender present:", "gender = " in h)
