# Setup and operations

## 1. Configuration

Copy `config.example.toml` to `config.toml`. The production configuration is
versioned as `deploy/config.production.toml`; it contains no secrets.

Required environment variables:

```text
ZAI_API_KEY=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

Optional provider credentials:

```text
REED_API_KEY=...
ADZUNA_APP_ID=...
ADZUNA_APP_KEY=...
JOOBLE_API_KEY=...
```

The Google Drive folder is public read-only, so no Google token, OAuth secret,
service-account JSON or API key is used. `gdown` reads the configured folder
URL. The sync must find exactly four supported CVs after the `geolog` filename
filter; otherwise it keeps the last known good CV snapshot and fails visibly.

## 2. Local verification

```bash
uv sync --extra dev
uv run work-researcher sync-drive
uv run work-researcher doctor
uv run pytest -q
uv run work-researcher run-once --dry-run
```

`run-once --dry-run` still performs live Drive, providers and GLM calls, but
does not send Telegram messages or mark jobs as delivered.

## Weekly market dashboard

`work-researcher weekly-market` creates an immutable dated snapshot plus the
public `market/site/data.json`. Production runs it every Friday at 19:00 in the
`Europe/London` timezone. Deployment installs the project-owned Nginx snippet,
validates the complete configuration with `nginx -t`, then reloads Nginx. The
dashboard is served at `https://devbot.remart.ovh/jobs/`; deployments update its
UI but never trigger an unscheduled market crawl.

The keyless production sources are Totaljobs, Reed HTML, Earthworks, GOV.UK
Find a job and the official Civil Service Careers Government Digital and Data
feed. Adzuna and Jooble remain enabled but report a visible credential warning
until their optional keys are configured.

## 3. Server layout

```text
/opt/work-researcher-bot/releases/<git-sha>  immutable releases
/opt/work-researcher-bot/current             active release symlink
/etc/work-researcher-bot/config.toml         production config
/etc/work-researcher-bot/env                 secrets, root:ubuntu 0640
/var/lib/work-researcher-bot/                SQLite, CVs and sync staging
/var/lib/work-researcher-bot/market/         weekly snapshots and public dashboard data
```

The oneshot service is `work-researcher-bot.service`; the timer is
`work-researcher-bot.timer`. Useful commands:

```bash
systemctl list-timers work-researcher-bot.timer
sudo systemctl start work-researcher-bot.service
journalctl -u work-researcher-bot.service -n 200 --no-pager
systemctl list-timers work-researcher-market.timer
journalctl -u work-researcher-market.service -n 200 --no-pager
```

Operational exceptions are logged and also sent to Telegram as a bounded alert.

## 4. GitHub Actions CI/CD

Repository secrets:

- `SERVER_HOST`
- `SERVER_USER`
- `SERVER_SSH_KEY`
- `SERVER_KNOWN_HOSTS`

Every push to `main` runs lint and tests, uploads a tarball over SSH, installs
the locked dependencies, atomically activates it and enables the timer. Five
most recent releases are retained. No runtime secret is copied through GitHub;
the server-owned environment file survives deployments.

## 5. ZCode and GLM

ZCode is a desktop Electron client. It may be installed on the server for
parity, but it is not used as the headless scheduler. The systemd service calls
the same Z.AI Coding Plan endpoint directly with model `glm-5.3-flash`, which is
the supported reliable server execution path.

## 6. Applications

The MCP browser/application functionality remains available locally:

```bash
uv run work-researcher serve --transport stdio
```

It is deliberately outside `work-researcher-bot.service`; nightly runs search
and report only, never submit an application.
