"""Local channel preview — pulls Oracle's live template so bot and laptop always match.

Usage (PowerShell, from this folder):
  python local_send_test.py              # syncs live template from Oracle, then sends + keep (prints mid)
  python local_send_test.py --no-sync    # skip Oracle pull, use local file only
  python local_send_test.py --delete 16  # delete a test message

Needs local .env with TELEGRAM_BOT_TOKEN + TELEGRAM_CHANNEL_ID (gitignored).
Or set env vars: $env:TELEGRAM_BOT_TOKEN="..."; $env:TELEGRAM_CHANNEL_ID="-100..."
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# anchor everything to this file's folder — not CWD
# (double-clicking from Explorer runs with CWD=C:\Windows → Path("data") → Access Denied)
BASE_DIR = Path(__file__).resolve().parent
# ensure imports resolve from this folder regardless of CWD
sys.path.insert(0, str(BASE_DIR))

from config import load_settings
from formatter import Position, render_call

try:
    from owner_commands import load_template
except ImportError:
    load_template = lambda: None  # fallback to formatter default


SAMPLE = Position(
    symbol="NIFTY 24500 CE",
    side="BUY",
    entry_price=142.5,
    qty=50,
    entry_time="2026-09-19 09:30:02",
    sl=118,
    exit_info="🔻SL hit @ 118",
)


def sync_live_template() -> bool:
    """Best-effort pull of Oracle's data/template.txt → local data/template.txt."""
    try:
        import paramiko

        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(
            "80.225.225.35",
            username="ubuntu",
            key_filename=r"C:\Users\nihal\.ssh\id_ed25519",
            timeout=8,
            banner_timeout=8,
            auth_timeout=8,
        )
        sftp = c.open_sftp()
        dest = BASE_DIR / "data" / "template.txt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        sftp.get("/opt/dhan-telegram/data/template.txt", str(dest))
        sftp.close()
        c.close()
        print(f"Synced live template from Oracle to {dest}")
        return True
    except Exception as e:
        # show CWD to diagnose the old bug (was C:\Windows when double-clicked)
        import traceback
        print(f"Live sync skipped ({e}) [cwd={Path.cwd()}] - using local template")
        # uncomment for full trace: traceback.print_exc()
        return False


async def send_preview():
    if "--no-sync" not in sys.argv:
        sync_live_template()
    s = load_settings()
    if not s.telegram_bot_token or not s.telegram_channel_id:
        print("Missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHANNEL_ID — create .env from .env.example or set env vars.")
        sys.exit(1)
    from telegram import Bot
    from telegram.constants import ParseMode

    tpl = None
    try:
        tpl = load_template()
    except Exception:
        tpl = None
    text = render_call(SAMPLE, tpl, s.chart_url if hasattr(s, "chart_url") else "https://web.dhan.co")
    bot = Bot(token=s.telegram_bot_token)
    msg = await bot.send_message(
        chat_id=s.telegram_channel_id,
        text=text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    print(f"SENT mid={msg.message_id}")
    try:
        print("Preview (first 400 chars):")
        print(text[:400].replace("\n", " | "))
    except UnicodeEncodeError:
        print(text[:400].encode("ascii", "backslashreplace").decode().replace("\n", " | "))
    return msg.message_id


async def delete_mid(mid: int):
    s = load_settings()
    from telegram import Bot

    bot = Bot(token=s.telegram_bot_token)
    await bot.delete_message(chat_id=s.telegram_channel_id, message_id=mid)
    print(f"deleted {mid}")


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--delete":
        asyncio.run(delete_mid(int(sys.argv[2])))
    else:
        asyncio.run(send_preview())
