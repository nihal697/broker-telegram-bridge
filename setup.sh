#!/usr/bin/env bash
# Oracle A1 Ubuntu setup — idempotent, safe to re-run (rebuild runbook).
# Works for any broker; Dhan adapter shown as example (default path /opt/broker-telegram,
# legacy /opt/dhan-telegram still works).
set -euo pipefail
APP=${APP:-/opt/broker-telegram}
# legacy alias — if /opt/dhan-telegram already exists, use it
if [ -d /opt/dhan-telegram ] && [ ! -d "$APP" ]; then APP=/opt/dhan-telegram; fi
sudo apt update && sudo apt install -y python3-venv python3-pip sqlite3
sudo mkdir -p "$APP/data" && sudo chown -R "$USER:$USER" "$APP"
cd "$APP"
[ -d venv ] || python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
[ -f .env ] || cp .env.example .env
chmod 600 .env || true
echo "--- dry-run self test ---"
./venv/bin/python -c "import test_main as t; t.test_e2e_send_then_edits(); print('SELFTEST OK')"
echo "Next: fill .env (BROKER=dhan and Telegram creds), then:"
echo "  sudo cp broker-telegram.service /etc/systemd/system/  # or dhan-telegram.service for legacy path"
echo "  sudo systemctl enable --now broker-telegram            # or dhan-telegram"
echo "  # Dhan only: sudo cp dhan-token-refresh.* /etc/systemd/system/ && sudo systemctl enable --now dhan-token-refresh.timer"
