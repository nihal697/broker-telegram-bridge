#!/usr/bin/env bash
# Oracle A1 Ubuntu setup — idempotent, safe to re-run (rebuild runbook).
set -euo pipefail
APP=/opt/dhan-telegram
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
echo "Next: fill .env, then:"
echo "  sudo cp dhan-telegram.service /etc/systemd/system/ && sudo systemctl enable --now dhan-telegram"
echo "  sudo cp dhan-token-refresh.* /etc/systemd/system/ && sudo systemctl enable --now dhan-token-refresh.timer"
