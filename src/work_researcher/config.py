"""Single-candidate configuration for the job-search agent.

Secrets are resolved from environment variables and must not be committed.
The bot intentionally supports one candidate only: Andrey Remnev.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(os.environ.get("WORK_RESEARCHER_CONFIG", PROJECT_ROOT / "config.toml"))

DEFAULTS: dict = {
    "general": {"candidate_name": "Andrey Remnev", "cv_dir": "CV_collection", "data_dir": "data", "log_level": "INFO"},
    "search": {
        "career_level": "entry", "default_location": "UK", "default_radius_miles": 40,
        "default_max_days_old": 7, "default_work_from_home": False,
        "default_limit_per_source": 50, "provider_timeout_s": 35,
        "exclude_training_offers": True, "exclude_agencies": True,
        "daily_commute_miles": 25, "occasional_commute_miles": 55,
    },
    "applicant": {
        "full_name": "Andrey Remnev", "email": "", "phone": "",
        "home_location": "Blackpool", "home_postcode": "", "max_commute_miles": 55,
        "daily_commute_miles": 25, "occasional_commute_miles": 55,
        "willing_to_relocate": False, "relocate_areas": [],
    },
    "browser": {"headless": False, "channel": "msedge", "default_timeout_ms": 15000},
    "auth": {"google_account": "", "auto_google_signin": True},
    "blocklist": {"companies": []},
    "providers": {
        "totaljobs": {"enabled": True}, "reed": {"enabled": True, "api_key": ""},
        "adzuna": {"enabled": True, "app_id": "", "app_key": ""},
        "jooble": {"enabled": True, "api_key": ""},
        "earthworks": {"enabled": True, "uk_only": True},
        "findajob": {"enabled": False, "browser_only": True},
    },
    "drive": {
        "enabled": True, "folder_url": "", "folder_id": "", "include_names": [],
        "exclude_name_patterns": ["geolog"], "required_count": 4,
    },
    "llm": {
        "enabled": True, "base_url": "https://api.z.ai/api/coding/paas/v4",
        "model": "glm-5.3-flash", "timeout_s": 150, "batch_size": 3,
        "max_attempts": 3, "max_tokens": 4096,
    },
    "telegram": {"enabled": True, "chat_id": "", "parse_mode": "HTML", "disable_web_page_preview": True},
    "report": {
        "max_jobs": 40, "max_per_path": 12,
        "pre_llm_max_per_path": 15, "include_seen": False,
    },
    "career_paths": {
        "data_engineering": {
            "label": "Data Engineering",
            "queries": ["Junior Data Engineer", "Associate Data Engineer", "Data Engineer I", "Trainee Data Engineer", "Data Integration Engineer", "ETL Developer", "Junior Azure Data Engineer"],
            "cv_name_contains": ["data engineer", "data_engineer"],
        },
        "geospatial_data": {
            "label": "Geospatial Data Engineering",
            "queries": ["Geospatial Data Analyst", "GIS Data Analyst", "Spatial Data Analyst", "GIS Analyst Python SQL", "Junior GIS Developer", "Environmental Data Analyst Python", "Geoscience Data Analyst"],
            "cv_name_contains": ["geospatial", "gis"],
        },
        "analytics": {
            "label": "Analytics to Data Engineering",
            "queries": ["Junior Data Analyst Python SQL", "Data Analyst Python SQL", "BI Analyst SQL", "Junior BI Developer", "Reporting Data Analyst SQL"],
            "cv_name_contains": ["analyst", "analytics", "data analysis"],
        },
        "software_data_platform": {
            "label": "Software Engineering to Data Platform",
            "queries": ["Junior Python Developer", "Backend Python Developer junior", "Software Engineer Data junior", "Python Data Developer", "Data Applications Developer", "Integration Developer junior"],
            "cv_name_contains": ["software", "python", "developer"],
        },
    },
}


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


@dataclass
class Settings:
    project_root: Path = PROJECT_ROOT
    config_path: Path = CONFIG_PATH
    data_dir: Path = PROJECT_ROOT / "data"
    cv_dir: Path = PROJECT_ROOT / "CV_collection"
    db_path: Path = PROJECT_ROOT / "data" / "work_researcher.db"
    log_level: str = "INFO"
    candidate_name: str = "Andrey Remnev"
    career_level: str = "entry"
    default_location: str = "UK"
    default_radius_miles: int = 40
    default_max_days_old: int = 7
    default_work_from_home: bool = False
    default_limit_per_source: int = 50
    provider_timeout_s: int = 35
    exclude_training: bool = True
    exclude_agencies: bool = True
    daily_commute_miles: int = 25
    occasional_commute_miles: int = 55
    applicant: dict = field(default_factory=dict)
    browser: dict = field(default_factory=dict)
    auth: dict = field(default_factory=dict)
    providers: dict = field(default_factory=dict)
    search_profiles: dict = field(default_factory=dict)
    blocklist_companies: list = field(default_factory=list)
    drive: dict = field(default_factory=dict)
    llm: dict = field(default_factory=dict)
    telegram: dict = field(default_factory=dict)
    report: dict = field(default_factory=dict)
    career_paths: dict = field(default_factory=dict)

    @property
    def browser_profile_dir(self) -> Path:
        return self.data_dir / "browser_profile"

    @property
    def screenshots_dir(self) -> Path:
        return self.data_dir / "screenshots"

    def provider_enabled(self, name: str) -> bool:
        return bool(self.providers.get(name, {}).get("enabled", False))

    def provider_cfg(self, name: str) -> dict:
        return self.providers.get(name, {})

    def secret(self, provider: str, key: str) -> str:
        value = os.environ.get(f"{provider}_{key}".upper(), "").strip()
        return value or str(self.providers.get(provider, {}).get(key, "") or "").strip()

    @property
    def telegram_token(self) -> str:
        return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

    @property
    def telegram_chat_id(self) -> str:
        return os.environ.get("TELEGRAM_CHAT_ID", "").strip() or str(self.telegram.get("chat_id", "")).strip()

    @property
    def zai_api_key(self) -> str:
        return os.environ.get("ZAI_API_KEY", "").strip()


def _read_config(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeError(f"Invalid TOML in {path}: {exc}") from exc


def load_settings(config_path: Path | None = None) -> Settings:
    path = config_path or CONFIG_PATH
    merged = _merge(DEFAULTS, _read_config(path))
    general, search = merged["general"], merged["search"]
    settings = Settings(
        config_path=path, data_dir=PROJECT_ROOT / general["data_dir"], cv_dir=PROJECT_ROOT / general["cv_dir"],
        log_level=general["log_level"], candidate_name=general.get("candidate_name", "Andrey Remnev"),
        career_level=search.get("career_level", "entry"), default_location=search["default_location"],
        default_radius_miles=int(search["default_radius_miles"]), default_max_days_old=int(search["default_max_days_old"]),
        default_work_from_home=bool(search["default_work_from_home"]), default_limit_per_source=int(search["default_limit_per_source"]),
        provider_timeout_s=int(search["provider_timeout_s"]), exclude_training=bool(search.get("exclude_training_offers", True)),
        exclude_agencies=bool(search.get("exclude_agencies", True)), daily_commute_miles=int(search.get("daily_commute_miles", 25)),
        occasional_commute_miles=int(search.get("occasional_commute_miles", 55)), applicant=merged["applicant"],
        browser=merged["browser"], auth=merged["auth"], providers=merged["providers"], search_profiles=search.get("profiles", {}),
        blocklist_companies=list(merged.get("blocklist", {}).get("companies", [])), drive=merged["drive"], llm=merged["llm"],
        telegram=merged["telegram"], report=merged["report"], career_paths=merged["career_paths"],
    )
    settings.db_path = settings.data_dir / "work_researcher.db"
    return settings


def ensure_dirs(settings: Settings) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.cv_dir.mkdir(parents=True, exist_ok=True)
    settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
