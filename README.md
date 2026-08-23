# Work Researcher MCP

Local MCP server for **UK job search, CV management and job applications**.
Built for an agent workflow: you ask "check new Data Analytics vacancies", the
agent searches multiple boards, shows a deduplicated ranked list, you pick the
ones you like, and the agent submits real applications through an embedded
browser (real Edge, persistent login profile).

## Feature highlights

- **Fast multi-board search** (plain HTTP/API, no browser): Totaljobs, Reed,
  Earthworks (geoscience). Adzuna + Jooble unlock with free API keys.
- **Browser-only boards** (Indeed, CV-Library, LinkedIn, Glassdoor): the
  harness agent searches them in a browser and feeds findings back via
  `submit_job_observations` — same store, same ranking.
- **Cross-board dedup**: the same vacancy on several boards merges into one
  canonical job (exact hash + rapidfuzz fuzzy match) — you never apply twice.
- **Application memory** (SQLite, survives restarts): every application is
  recorded; searches show `already_applied` + `application_status`;
  `start_application` refuses second applications; `check_applied` answers
  "have we applied here?" by URL or fuzzy title+company.
- **Location intelligence**: home = Blackpool (config). `work_mode`
  (remote/hybrid/on-site/field), `distance_miles` (postcodes.io geocoding,
  cached), `location_status` ok|mismatch|caution. Remote jobs are searched
  UK-wide; on-site beyond `max_commute_miles` are penalised and flagged —
  never submitted without explicit user approval.
- **Blocklist**: "never apply to Penguin Recruitment" →
  `manage_blocklist(action=add, kind=company)` — persisted forever, blocked
  employers are hidden from results and refuses in start_application.
- **Training-ad guard**: paid course ads (where the candidate pays —
  Netcom-style providers, fee/loan language, trainee titles with bait salary
  ranges like £30-65k) are excluded automatically with a
  `training_offers_skipped` count; real paid apprenticeships stay.
  `search_jobs(include_training=true)` opts in explicitly.
- **CV management**: local `CV_collection` + Google Drive sync (folder "CV" on
  ry4ara@gmail.com). Read AND write: pull → edit docx locally →
  `push_cv_to_drive`. CVs are parsed, domain-tagged (data_analytics / geology
  / engineering) and matched to vacancies.
- **Agent-optimized browser**: persistent Edge profile, "Sign in with Google"
  picks the pre-approved account (7255591@gmail.com) without asking; every
  action returns a fresh compact snapshot (no re-snapshot round-trips);
  `browser_form` shows application forms with human labels; popups auto-adopt.

## Tools (26, prefix-grouped)

- search: `get_status`, `search_jobs` (also pages results via `search_id`),
  `get_job` (1-5 ids, side-by-side), `submit_job_observations`
- cv: `list_cvs` (+per-job recommendations), `sync_cvs` (local/drive/both),
  `push_cv_to_drive`
- apply: `start_application` (plan + anti-double-apply + blocklist + location
  guard), `record_application`, `list_applications`, `check_applied`,
  `manage_blocklist`
- browser: `browser_login`, `browser_open`, `browser_snapshot`,
  `browser_form`, `browser_click`, `browser_set`, `browser_type`,
  `browser_upload`, `browser_press`, `browser_wait`, `browser_screenshot`,
  `browser_eval`, `browser_tabs`, `browser_close`

## Intended agent workflow

1. `search_jobs(profile="data_analytics")` or a free-text query
2. Present the ranked list (duplicates merged, already_applied, location_status)
3. User picks vacancies
4. `start_application(job_id)` per pick → URL, method, CV, applicant profile,
   site playbook, cautions
5. `browser_login(url)` if the board needs auth (Google account is pre-approved)
6. `browser_form` + `browser_set`… + `browser_screenshot` at the confirmation
7. `record_application(status="submitted", evidence={screenshot})`

## Quick start

```bash
uv sync
uv run playwright install chromium   # fallback browser (Edge is used by default)
uv run work-researcher doctor        # config / DB / providers / drive report
uv run work-researcher selftest      # in-process smoke test
uv run python scripts/e2e_test.py    # full live MCP round-trip (no submissions)
uv run work-researcher serve --transport stdio
```

Configuration: `config.toml` (annotated copy: `config.example.toml`).
Credentials/API keys: `SETUP.md`. Board coverage map: `JOB_SITES.md`.

## Connected harnesses (this machine)

Stdio command:
`C:\Users\andre\miniconda3\Scripts\uv.exe run --directory D:\PYTHON\WORK_RESEARCHER_MCP work-researcher serve --transport stdio`

- **ZCode** — `~/.zcode/cli/config.json` → `mcp.servers["work-researcher"]`
- **OpenCode** — `~/.config/opencode/opencode.jsonc` → `mcp` block (local)
- **DeepSeek Harness (dsh)** — `~/.dsh/profiles/{headless,web}/cordis.patch.yml`
  → `@deepseek-ai/dsh-mcp-client` plugin (tools appear as
  `mcp__work-researcher__*`)

## Architecture

```
src/work_researcher/
  server.py        MCP wiring, 26 tools        browser.py   Playwright (Edge, persistent)
  providers/       totaljobs reed adzuna       tracker.py   apply plans + guards
                   jooble earthworks           dedup.py     cross-board duplicate merge
  persistence.py   SQLite (jobs/searches/apps/ geo.py       geocoding + commute policy
                   cvs/blocklist/locations)    cvmanager.py CV parse + tagging
  drive.py         Google Drive read/write     ranking.py   relevance scoring
  config.py        config.toml + env           cli.py       serve/doctor/search/…
```
