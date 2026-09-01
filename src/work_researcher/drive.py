"""Read-only synchronization from a publicly shared Google Drive folder."""

from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path

from .config import Settings

SUPPORTED_SUFFIXES = {".docx", ".pdf", ".doc"}


class DriveSyncError(RuntimeError):
    """The public Drive folder could not produce a safe four-CV snapshot."""


def _folder_url(settings: Settings) -> str:
    configured = str(settings.drive.get("folder_url", "")).strip()
    if configured:
        return configured.replace("\\_", "_")
    folder_id = str(settings.drive.get("folder_id", "")).strip()
    if not folder_id:
        raise DriveSyncError("drive.folder_url or drive.folder_id is required")
    return f"https://drive.google.com/drive/folders/{folder_id}"


def _select(settings: Settings, files: list[Path]) -> list[Path]:
    include = {
        str(value).casefold()
        for value in settings.drive.get("include_names", [])
        if str(value).strip()
    }
    excludes = [re.compile(str(value), re.I) for value in settings.drive.get("exclude_name_patterns", [])]
    selected = []
    for path in files:
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        if include and path.name.casefold() not in include:
            continue
        if any(pattern.search(path.name) for pattern in excludes):
            continue
        selected.append(path)
    required = int(settings.drive.get("required_count", 4))
    if len(selected) != required:
        names = ", ".join(sorted(path.name for path in selected)) or "none"
        raise DriveSyncError(
            f"expected exactly {required} career CVs after filtering, found {len(selected)}: {names}"
        )
    return sorted(selected)


def _sync(settings: Settings) -> dict:
    import gdown

    stage = settings.data_dir / "cv-sync-stage"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True, exist_ok=True)
    url = _folder_url(settings)
    try:
        downloaded = gdown.download_folder(
            url=url,
            output=str(stage),
            quiet=True,
            use_cookies=False,
            remaining_ok=False,
        )
    except Exception as exc:
        raise DriveSyncError(f"public Drive download failed: {exc}") from exc
    if not downloaded:
        raise DriveSyncError(
            "public Drive folder returned no files; verify that 'Anyone with the link' has Viewer access"
        )

    selected = _select(settings, [Path(path) for path in downloaded])
    from .cvmanager import extract_text

    records = []
    for path in selected:
        if path.stat().st_size < 1024:
            raise DriveSyncError(f"downloaded CV is unexpectedly small: {path.name}")
        if path.suffix.lower() in {".docx", ".pdf"} and len(extract_text(path).strip()) < 200:
            raise DriveSyncError(f"CV could not be parsed or contains too little text: {path.name}")
        records.append({"name": path.name, "size": path.stat().st_size})

    # Replace the prior snapshot only after all four new files validate.
    settings.cv_dir.mkdir(parents=True, exist_ok=True)
    wanted = {item["name"] for item in records}
    for existing in settings.cv_dir.iterdir():
        if (
            existing.is_file()
            and existing.suffix.lower() in SUPPORTED_SUFFIXES
            and existing.name not in wanted
        ):
            existing.unlink()
    for source in selected:
        target = settings.cv_dir / source.name
        temporary = target.with_suffix(target.suffix + ".part")
        shutil.copyfile(source, temporary)
        temporary.replace(target)
    return {"ok": True, "folder_url": url, "files": records}


async def sync_cvs_from_drive(settings: Settings) -> dict:
    """Download, validate, atomically publish and re-index the four CVs."""
    if not settings.drive.get("enabled", True):
        return {"ok": False, "disabled": True}
    result = await asyncio.to_thread(_sync, settings)
    from .cvmanager import index_cvs

    result["index"] = await index_cvs(settings, force=True)
    return result
