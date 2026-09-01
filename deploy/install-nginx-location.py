"""Idempotently attach the project-owned /jobs snippet to devbot's TLS server."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

SITE = Path("/etc/nginx/sites-available/devbot.remart.ovh")
INCLUDE = "    include /etc/nginx/snippets/work-researcher-jobs.conf;"
FALLBACK = "    location / {\n        return 404;\n    }\n"


def install(site: Path) -> None:
    text = site.read_text(encoding="utf-8")
    if INCLUDE in text:
        return
    if text.count(FALLBACK) != 1:
        raise RuntimeError("could not safely locate devbot TLS fallback location")
    backup = site.with_suffix(site.suffix + ".before-work-researcher")
    if not backup.exists():
        shutil.copy2(site, backup)
    updated = text.replace(FALLBACK, f"{INCLUDE}\n\n{FALLBACK}")
    temporary = site.with_suffix(site.suffix + ".tmp")
    temporary.write_text(updated, encoding="utf-8")
    os.replace(temporary, site)


def main() -> None:
    install(SITE)


if __name__ == "__main__":
    main()
