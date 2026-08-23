import io

path = r"src\work_researcher\server.py"
h = io.open(path, encoding="utf-8").read()

old = '''    async def browser_snapshot(focus: str | None = None,
                               filter_text: str | None = None,
                               text_chars: int = 800) -> dict:
        """Look at the page: numbered interactive elements + text. focus:
        'inputs'|'buttons'|'links'; filter_text narrows by name (find 'Apply');
        text_chars=0 → elements only, 6000 → reading mode."""'''
new = '''    async def browser_snapshot(focus: str | None = None,
                               filter_text: str | None = None,
                               text_chars: int = 800,
                               modal_only: bool = False) -> dict:
        """Look at the page: numbered interactive elements + text. focus:
        'inputs'|'buttons'|'links'; filter_text narrows by name (find 'Apply');
        text_chars=0 → elements only, 6000 → reading mode. modal_only=true →
        ONLY the active dialog/wizard (question text + controls, hidden
        templates excluded) — use for apply wizards, then browser_set/click
        by number."""'''
if old in h:
    h = h.replace(old, new, 1)
    io.open(path, "w", encoding="utf-8").write(h)
    print("snapshot tool updated")
else:
    print("pattern not found — checking actual signature")
    i = h.find("async def browser_snapshot")
    print(h[i:i+300])
