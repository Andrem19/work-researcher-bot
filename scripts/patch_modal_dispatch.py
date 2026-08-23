import io

path = r"src\work_researcher\server.py"
h = io.open(path, encoding="utf-8").read()
old = ('            return await get_session(settings).snapshot(focus, filter_text, '
       'text_chars)')
new = ('            return await get_session(settings).snapshot(focus, filter_text, '
       'text_chars, modal_only)')
if old in h:
    h = h.replace(old, new, 1)
    io.open(path, "w", encoding="utf-8").write(h)
    print("dispatch updated")
else:
    print("not found")
