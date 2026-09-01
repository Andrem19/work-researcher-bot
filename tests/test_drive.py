from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from work_researcher.drive import _sync


def test_sync_uses_disposable_stage_and_removes_it(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    cv_dir = tmp_path / "cvs"
    data_dir.mkdir()
    # A legacy shared staging directory must not affect a new synchronization.
    (data_dir / "cv-sync-stage").mkdir()

    def download_folder(*, output, **_kwargs):
        downloaded = Path(output) / "career.doc"
        downloaded.write_bytes(b"CV content " * 200)
        return [str(downloaded)]

    monkeypatch.setitem(
        sys.modules,
        "gdown",
        SimpleNamespace(download_folder=download_folder),
    )
    settings = SimpleNamespace(
        data_dir=data_dir,
        cv_dir=cv_dir,
        drive={
            "folder_url": "https://drive.google.com/drive/folders/test",
            "include_names": ["career.doc"],
            "exclude_name_patterns": [],
            "required_count": 1,
        },
    )

    result = _sync(settings)

    assert result["ok"] is True
    assert (cv_dir / "career.doc").is_file()
    assert list(data_dir.glob("cv-sync-stage-*")) == []
