#!/usr/bin/env bash
set -euo pipefail

upload="${1:-/home/ubuntu/yh-autoresearch-upload}"
app_root=/opt/yh-autoresearch
access_root="$app_root/access"
release_root="$app_root/releases"
bundle_name=yh-autoresearch-0.4.0.zip
bundle="$release_root/$bundle_name"
env_dir=/etc/yh-autoresearch
env_file="$env_dir/access.env"
unit=/etc/systemd/system/yh-autoresearch-access.service
snippet=/etc/nginx/snippets/yh-autoresearch.conf
site=/etc/nginx/sites-available/yh-intel-portal
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup="/var/backups/yh-autoresearch/$stamp"

test -f "$upload/server/access_host.py"
test -f "$upload/server/__init__.py"
test -f "$upload/$bundle_name"
test -f "$upload/yh-autoresearch-access.service"
test -f "$upload/yh-autoresearch.conf"
test "$(sha256sum "$upload/$bundle_name" | awk '{print $1}')" = "4a65c8ecde4d8764a6219d9e452fe1118aa75aeaf1effbbb4de73358695b4fed"
sudo -n true
sudo nginx -t

sudo install -d -o root -g root -m 0755 "$backup"
for source in "$site" "$unit" "$snippet" "$env_file"; do
  if sudo test -f "$source"; then sudo cp -a "$source" "$backup/$(basename "$source")"; fi
done
if sudo test -d "$app_root"; then sudo cp -a "$app_root" "$backup/app_root"; fi

rollback() {
  echo "YH Autoresearch deployment failed; restoring snapshot $backup" >&2
  if sudo test -d "$backup/app_root"; then
    sudo rm -rf "$app_root"
    sudo cp -a "$backup/app_root" "$app_root"
  else
    sudo rm -rf "$app_root"
  fi
  for target in "$unit" "$snippet" "$env_file"; do
    saved="$backup/$(basename "$target")"
    if sudo test -f "$saved"; then
      if test "$target" = "$env_file"; then sudo install -o root -g www-data -m 0640 "$saved" "$target"; else sudo install -o root -g root -m 0644 "$saved" "$target"; fi
    else
      sudo rm -f "$target"
    fi
  done
  if sudo test -f "$backup/$(basename "$site")"; then sudo cp -a "$backup/$(basename "$site")" "$site"; fi
  sudo systemctl daemon-reload || true
  if sudo test -f "$unit"; then sudo systemctl restart yh-autoresearch-access.service || true; else sudo systemctl disable --now yh-autoresearch-access.service 2>/dev/null || true; fi
  sudo nginx -t && sudo systemctl reload nginx || true
}
trap rollback ERR

sudo install -d -o root -g root -m 0755 "$app_root" "$access_root" "$release_root"
sudo install -d -o root -g www-data -m 0750 "$env_dir"
sudo install -d -o root -g root -m 0755 "$access_root/server"
sudo install -o root -g root -m 0644 "$upload/server/__init__.py" "$access_root/server/__init__.py"
sudo install -o root -g root -m 0644 "$upload/server/access_host.py" "$access_root/server/access_host.py"
sudo install -o root -g root -m 0644 "$upload/$bundle_name" "$bundle"
sudo install -o root -g root -m 0644 "$upload/yh-autoresearch-access.service" "$unit"
sudo install -o root -g root -m 0644 "$upload/yh-autoresearch.conf" "$snippet"

if ! sudo test -f "$env_file"; then
  test -n "${YH_DEPLOY_ACCESS_CODE:-}"
  session_secret="$(openssl rand -hex 32)"
  env_tmp="$(mktemp)"
  {
    printf 'YH_ACCESS_CODE=%s\n' "$YH_DEPLOY_ACCESS_CODE"
    printf 'YH_SESSION_SECRET=%s\n' "$session_secret"
    printf 'YH_BUNDLE_PATH=%s\n' "$bundle"
    printf 'YH_SECURE_COOKIE=1\n'
    printf 'YH_PUBLIC_PREFIX=/release/yh-autoresearch\n'
  } > "$env_tmp"
  sudo install -o root -g www-data -m 0640 "$env_tmp" "$env_file"
  rm -f "$env_tmp"
else
  sudo sed -i "s|^YH_BUNDLE_PATH=.*|YH_BUNDLE_PATH=$bundle|" "$env_file"
  if ! sudo grep -q '^YH_PUBLIC_PREFIX=' "$env_file"; then echo 'YH_PUBLIC_PREFIX=/release/yh-autoresearch' | sudo tee -a "$env_file" >/dev/null; fi
fi

if ! sudo grep -qF 'include /etc/nginx/snippets/yh-autoresearch.conf;' "$site"; then
  sudo sed -i '/include \/etc\/nginx\/snippets\/yh-service-commons.conf;/a\    include /etc/nginx/snippets/yh-autoresearch.conf;' "$site"
fi

sudo systemctl daemon-reload
sudo systemctl enable --now yh-autoresearch-access.service
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:18788/healthz | grep -q '"ok":true'; then break; fi
  sleep 0.2
done
curl -fsS http://127.0.0.1:18788/healthz | grep -q '"ok":true'
sudo nginx -t
sudo systemctl reload nginx

public_status="$(curl -ksS -o /tmp/yh-autoresearch-index.html -w '%{http_code}' https://43.153.65.53/release/yh-autoresearch/)"
test "$public_status" = 200
grep -q '<title>YH Autoresearch Internal Beta</title>' /tmp/yh-autoresearch-index.html
unauth_status="$(curl -ksS -o /dev/null -w '%{http_code}' https://43.153.65.53/release/yh-autoresearch/api/bundle)"
test "$unauth_status" = 401
sudo systemctl is-active --quiet yh-autoresearch-access.service
sudo systemctl is-active --quiet nginx
trap - ERR

echo "YH Autoresearch deployed: https://43.153.65.53/release/yh-autoresearch/"
echo "bundle_sha256=$(sha256sum "$bundle" | awk '{print $1}')"
echo "rollback_snapshot=$backup"
