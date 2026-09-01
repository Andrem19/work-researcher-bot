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
sudo chown ubuntu:www-data /var/lib/work-researcher-bot
sudo install -d -o ubuntu -g www-data -m 0750 /var/lib/work-researcher-bot/market
sudo install -d -o ubuntu -g www-data -m 0750 /var/lib/work-researcher-bot/market/site
sudo install -d -o ubuntu -g ubuntu -m 0750 /var/lib/work-researcher-bot/market/history
sudo install -o ubuntu -g www-data -m 0644 dashboard/index.html /var/lib/work-researcher-bot/market/site/index.html
sudo install -d -o root -g ubuntu -m 0750 /etc/work-researcher-bot
sudo install -o root -g ubuntu -m 0640 deploy/config.production.toml /etc/work-researcher-bot/config.toml
sudo install -o root -g root -m 0644 deploy/work-researcher-bot.service /etc/systemd/system/work-researcher-bot.service
sudo install -o root -g root -m 0644 deploy/work-researcher-bot.timer /etc/systemd/system/work-researcher-bot.timer
sudo install -o root -g root -m 0644 deploy/work-researcher-market.service /etc/systemd/system/work-researcher-market.service
sudo install -o root -g root -m 0644 deploy/work-researcher-market.timer /etc/systemd/system/work-researcher-market.timer
nginx_site=/etc/nginx/sites-available/devbot.remart.ovh
nginx_restore="$(mktemp)"
trap 'rm -f -- "$nginx_restore"' EXIT
sudo cat "$nginx_site" > "$nginx_restore"
sudo install -o root -g root -m 0644 deploy/work-researcher-jobs.nginx.conf /etc/nginx/snippets/work-researcher-jobs.conf
sudo python3 deploy/install-nginx-location.py
if ! sudo nginx -t; then
  sudo cp "$nginx_restore" "$nginx_site"
  sudo nginx -t
  rm -f -- "$nginx_restore"
  exit 1
fi
rm -f -- "$nginx_restore"
trap - EXIT

ln -sfn "$release_dir" "$app_root/current.next"
mv -Tf "$app_root/current.next" "$app_root/current"
sudo systemctl daemon-reload
sudo systemctl enable --now work-researcher-bot.timer
sudo systemctl enable --now work-researcher-market.timer
sudo systemctl reload nginx
WORK_RESEARCHER_CONFIG=/etc/work-researcher-bot/config.toml "$app_root/current/.venv/bin/work-researcher" doctor

find "$app_root/releases" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' \
  | sort -nr | tail -n +6 | cut -d' ' -f2- \
  | while IFS= read -r old_release; do
      case "$old_release" in
        "$app_root/releases/"*) sudo rm -rf -- "$old_release" ;;
        *) echo "refusing to remove unexpected release path: $old_release" >&2; exit 1 ;;
      esac
    done
