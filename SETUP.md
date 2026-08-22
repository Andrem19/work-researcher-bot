# Setup Guide

Everything works out of the box for search (Totaljobs, Reed HTML, Earthworks —
no keys needed). The steps below unlock the rest.

## 1. Applicant profile (2 minutes)

Edit `config.toml` → `[applicant]`: `full_name`, `email` (the one employers
should reply to), `phone`, `notice_period`, `salary_expectation`, `linkedin`.
These values are injected into every apply plan. Location intelligence
(`home_location`, `max_commute_miles`, `willing_to_relocate`, `relocate_areas`)
also lives here.

## 2. Free API keys (5 minutes, optional but recommended)

| Provider | Where to get | Where to put |
|---|---|---|
| Adzuna | https://developer.adzuna.com (sign up → Application) | `config.toml` `[providers.adzuna]` `app_id`/`app_key` or env `ADZUNA_APP_ID`/`ADZUNA_APP_KEY` |
| Reed | https://www.reed.co.uk/developers (free partner key) | `[providers.reed]` `api_key` or env `REED_API_KEY` |
| Jooble | https://jooble.org/api/about (request a key) | `[providers.jooble]` `api_key` or env `JOOBLE_API_KEY` |

Without keys the server still searches Totaljobs + Reed(HTML) + Earthworks and
tells you which providers are missing credentials in `get_status`.

## 3. Google Drive CV sync (read AND write)

CVs live in the Drive folder **"CV"** on **ry4ara@gmail.com**. Two auth modes:

### Option A — OAuth (recommended, personal account)

1. Go to https://console.cloud.google.com → create/select a project.
2. **APIs & Services → Library** → enable **Google Drive API**.
3. **APIs & Services → OAuth consent screen** → External → fill the minimal
   fields → add ry4ara@gmail.com as a **test user**.
4. **APIs & Services → Credentials → Create credentials → OAuth client ID** →
   type **Desktop app** → download the JSON.
5. Save it as `secrets/google_credentials.json` in this project.
6. Run once (opens a browser for consent as ry4ara@gmail.com):
   ```
   uv run work-researcher drive-auth
   ```
   The token is cached at `secrets/google_token.json`.

### Option B — Service account

1. Create a service account in the same project, enable the Drive API.
2. Download the JSON key → `secrets/google_service_account.json`.
3. In `config.toml` set `drive.mode = "service_account"`.
4. **Share** the Drive folder "CV" with the service-account e-mail
   (like `xxx@yyy.iam.gserviceaccount.com`) — otherwise it sees nothing.

After setup: `sync_cvs` (MCP) or `uv run work-researcher drive-sync` pulls CVs
into `CV_collection/` and indexes them. Editing loop: the agent edits the docx
locally (python-docx), then `push_cv_to_drive` writes it back (update if the
file is known, create otherwise; refuses to clobber a Drive copy that changed
after our last pull unless `force=true`).

## 4. Board logins for applications

The embedded browser keeps a persistent login profile
(`data/browser_profile`, real Edge). `browser_login(url)` walks
"Sign in with Google" and picks the pre-approved account
(`[auth].google_account = 7255591@gmail.com`) WITHOUT asking; on 2FA/captcha
it stops and asks you to finish in the visible window. The profile persists,
so each board is signed in once.

## 5. Verify

```
uv run work-researcher doctor     # config / DB / providers / drive report
uv run work-researcher selftest   # in-process smoke test
uv run python scripts/e2e_test.py # full live MCP round-trip (no submissions)
```

## Where things live

- `config.toml` — all settings (see the commented `config.example.toml`)
- `secrets/` — Google credentials (never commit)
- `data/work_researcher.db` — jobs, searches, applications, CV index, blocklist
- `data/browser_profile/` — persistent browser logins
- `data/screenshots/` — application evidence
