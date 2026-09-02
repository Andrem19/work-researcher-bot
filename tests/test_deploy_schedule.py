from configparser import ConfigParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(("name", "calendar"), [
    ("work-researcher-bot", "*-*-* 20:00:00 Europe/London"),
    ("work-researcher-market", "Fri *-*-* 20:00:00 Europe/London"),
])
def test_production_timers_run_at_8pm_uk(name, calendar):
    timer = ConfigParser()
    timer.read(ROOT / "deploy" / f"{name}.timer", encoding="utf-8")
    assert timer["Timer"]["OnCalendar"] == calendar
    assert timer["Timer"]["Unit"] == f"{name}.service"
    assert timer["Timer"].getboolean("Persistent")
    assert timer["Install"]["WantedBy"] == "timers.target"
