"""Settings: config.toml at the project root, environment variable overrides.

The project root is the parent of src/ (editable install keeps this stable),
so the server works regardless of the harness's working directory. Secrets
live in config.toml (gitignored) or in environment variables; env always wins.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(os.environ.get("WORK_RESEARCHER_CONFIG", PROJECT_ROOT / "config.toml"))

DEFAULTS: dict = {
    "general": {
        "cv_dir": "CV_collection",
        "data_dir": "data",
        "log_level": "INFO",
    },
    "search": {
        "default_location": "UK",
        "default_radius_miles": 40,
        "default_max_days_old": 14,
        "default_work_from_home": False,
        "default_limit_per_source": 25,
        "provider_timeout_s": 30,
        "exclude_training_offers": True,
    },
    "applicant": {
        "full_name": "",
        "email": "",
        "phone": "",
        "location": "Blackpool, UK",
        "home_location": "Blackpool",
        "home_postcode": "",
        "max_commute_miles": 40,
        "daily_commute_miles": 25,
        "occasional_commute_miles": 50,
        "willing_to_relocate": False,
        "relocate_areas": [],
        "right_to_work": "Yes, I have the right to work in the UK",
        "notice_period": "",
        "salary_expectation": "",
        "linkedin": "",
    },
    "drive": {
        "enabled": True,
        "mode": "oauth",  # oauth | service_account | off
        "account": "ry4ara@gmail.com",
        "folder_name": "CV",
        "folder_id": "",
        "credentials_file": "secrets/google_credentials.json",
        "token_file": "secrets/google_token.json",
        "service_account_file": "secrets/google_service_account.json",
    },
    "browser": {
        "headless": False,
        "channel": "msedge",  # real Edge passes WDAC + board anti-bot; falls
        # back to bundled Chromium when Edge is absent
        "default_timeout_ms": 15000,
    },
    "auth": {
        # Pre-approved by the user: the agent may click "Sign in with Google"
        # and pick this account on job boards WITHOUT asking permission.
        # 2FA/captcha still stops and asks the user.
        "google_account": "7255591@gmail.com",
        "auto_google_signin": True,
    },
    "blocklist": {
        # Seeded into the DB blocklist on first use; runtime additions go
        # through the manage_blocklist MCP tool and persist in the DB.
        "companies": [],
    },
    "providers": {
        "totaljobs": {"enabled": True},
        "reed": {"enabled": True, "api_key": ""},
        "adzuna": {"enabled": True, "app_id": "", "app_key": ""},
        "jooble": {"enabled": True, "api_key": ""},
        "earthworks": {"enabled": True, "uk_only": True},
        "findajob": {"enabled": True, "browser_only": True},
    },
}


@dataclass
class Settings:
    project_root: Path = PROJECT_ROOT
    config_path: Path = CONFIG_PATH
    data_dir: Path = PROJECT_ROOT / "data"
    cv_dir: Path = PROJECT_ROOT / "CV_collection"
    db_path: Path = PROJECT_ROOT / "data" / "work_researcher.db"
    log_level: str = "INFO"

    default_location: str = "UK"
    default_radius_miles: int = 40
    default_max_days_old: int = 14
    default_work_from_home: bool = False
    default_limit_per_source: int = 25
    provider_timeout_s: int = 30
    exclude_training: bool = True
    daily_commute_miles: int = 25
    occasional_commute_miles: int = 50

    applicant: dict = field(default_factory=dict)
    drive: dict = field(default_factory=dict)
    browser: dict = field(default_factory=dict)
    auth: dict = field(default_factory=dict)
    providers: dict = field(default_factory=dict)
    search_profiles: dict = field(default_factory=dict)
    blocklist_companies: list = field(default_factory=list)

    # -- derived helpers -------------------------------------------------
    @property
    def secrets_dir(self) -> Path:
        return self.project_root / "secrets"

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
        """Secret resolution: env <PROVIDER>_<KEY> wins over config.toml."""
        env_name = f"{provider}_{key}".upper()
        env_val = os.environ.get(env_name, "").strip()
        if env_val:
            return env_val
        return str(self.providers.get(provider, {}).get(key, "") or "").strip()


def _merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load_settings(config_path: Path | None = None) -> Settings:
    path = config_path or CONFIG_PATH
    raw: dict = {}
    if path.exists():
        try:
            with open(path, "rb") as fh:
                raw = tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            raise RuntimeError(f"Invalid TOML in {path}: {exc}") from exc
    merged = _merge(DEFAULTS, raw)

    general = merged["general"]
    search = merged["search"]
    s = Settings(
        project_root=PROJECT_ROOT,
        config_path=path,
        data_dir=PROJECT_ROOT / general["data_dir"],
        cv_dir=PROJECT_ROOT / general["cv_dir"],
        log_level=general["log_level"],
        default_location=search["default_location"],
        default_radius_miles=search["default_radius_miles"],
        default_max_days_old=search["default_max_days_old"],
        default_work_from_home=search["default_work_from_home"],
        default_limit_per_source=search["default_limit_per_source"],
        provider_timeout_s=search["provider_timeout_s"],
        exclude_training=search.get("exclude_training_offers", True),
        daily_commute_miles=int(search.get("daily_commute_miles",
                                          merged["applicant"].get("daily_commute_miles", 25))),
        occasional_commute_miles=int(search.get(
            "occasional_commute_miles",
            merged["applicant"].get("occasional_commute_miles", 50))),
        applicant=merged["applicant"],
        drive=merged["drive"],
        browser=merged["browser"],
        auth=merged["auth"],
        providers=merged["providers"],
        search_profiles=merged.get("search", {}).get("profiles", {}),
        blocklist_companies=list(merged.get("blocklist", {}).get("companies", [])),
    )
    s.db_path = s.data_dir / "work_researcher.db"
    return s


def ensure_dirs(settings: Settings) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.cv_dir.mkdir(parents=True, exist_ok=True)
    settings.screenshots_dir.mkdir(parents=True, exist_ok=True)
