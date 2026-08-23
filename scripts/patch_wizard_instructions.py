import io

path = r"src\work_researcher\server.py"
h = io.open(path, encoding="utf-8").read()

anchor = "CRITICAL: NEVER use the separate playwright MCP"
addition = (
    "WIZARD PROTOCOL (Reed apply questions and any modal-based form): use "
    "browser_snapshot(modal_only=true) — it isolates the ACTIVE wizard "
    "(question text + numbered controls, hidden templates like 'Session "
    "expired' excluded) — then browser_set/browser_click by number. NEVER "
    "hand-roll modal-finding JS via browser_eval (slow, fragile, and hidden "
    "templates mislead it). NEVER close a wizard modal: its X loses ALL "
    "progress and it restarts from Q1. NEVER click unnamed/empty buttons. "
    "Required multi-selects without a visible none-option: SCROLL the list "
    "first ('prefer not to say' / 'none of these' usually sits below the "
    "fold). "
)
if addition not in h and anchor in h:
    h = h.replace(anchor, addition + anchor, 1)
    io.open(path, "w", encoding="utf-8").write(h)
    print("wizard protocol added to instructions")
else:
    print("already or no anchor:", addition in h, anchor in h)
