#!/usr/bin/env bash
set -euo pipefail

release_dir="${1:?release directory is required}"
app_root=/opt/work-researcher-bot

test -d "$release_dir"
test -f "$release_dir/pyproject.toml"
test -f "$release_dir/deploy/work-researcher-bot.service"

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"
uv python install 3.12
cd "$release_dir"
uv sync --frozen --no-dev

sudo install -d -o ubuntu -g ubuntu -m 0750 /var/lib/work-researcher-bot
sudo install -d -o ubuntu -g ubuntu -m 0750 /var/lib/work-researcher-bot/CV_collection
sudo install -d -o root -g ubuntu -m 0750 /etc/work-researcher-bot
sudo install -o root -g ubuntu -m 0640 deploy/config.production.toml /etc/work-researcher-bot/config.toml
sudo install -o root -g root -m 0644 deploy/work-researcher-bot.service /etc/systemd/system/work-researcher-bot.service
sudo install -o root -g root -m 0644 deploy/work-researcher-bot.timer /etc/systemd/system/work-researcher-bot.timer

ln -sfn "$release_dir" "$app_root/current.next"
mv -Tf "$app_root/current.next" "$app_root/current"
sudo systemctl daemon-reload
sudo systemctl enable --now work-researcher-bot.timer
WORK_RESEARCHER_CONFIG=/etc/work-researcher-bot/config.toml "$app_root/current/.venv/bin/work-researcher" doctor

find "$app_root/releases" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' \
  | sort -nr | tail -n +6 | cut -d' ' -f2- \
  | while IFS= read -r old_release; do rm -rf -- "$old_release"; done
