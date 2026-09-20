# Dhan to Telegram Bridge

Auto-posts every manual trade you take on Dhan to your Telegram channel. Entry is sent instantly, and the same message is edited when the stop-loss is placed or hit. Targets are computed from risk-reward, not from pending limit orders.

Built for Indian retail traders who run a Telegram community and want zero manual copy-paste.

## Features

- **Instant entry** on `TRADED` / `PART_TRADED`. Pending entries are not spammed.
- **Same-message edits** when SL arrives (`STOP_LOSS_MARKET` with `TriggerPrice`) or when SL is hit.
- **RR-computed targets**: `T1 = 1.5R`, `T2 = 2R` (direction-aware, handles BUY/SELL). No dependency on limit prices.
- **Super Order support** via `AlgoOrdNo` linking (entry + SL + target in one Super Order).
- **Normal order grouping** via symbol + side + time window (default 120s, extended to 4h for late SL).
- **Deduplication** via `data/state.db` (`order_no, status, qty`). Restarts still edit the same Telegram message ID.
- **Telegram-editable template** — DM the bot `/template` to change layout without redeploy. Hot-reloaded, validation for unknown placeholders.
- **Dry-run mode** (`DRY_RUN=true` prints to console instead of hitting Telegram) for safe local testing.
- **Oracle-ready**: `systemd` services + daily `RenewToken` timer, no inbound ports.

## Architecture

```
Dhan App / Web (manual trade)
 └─ Live Order Update WS  wss://api-order-update.dhan.co  (MsgCode 42, SELF)
     └─ dhan_ws.py (auth + reconnect with backoff)
         └─ main.py (dedupe → PositionTracker → formatter)
             └─ grouper.py (one open slot per symbol|side, 4h late-SL window)
                 └─ formatter.py + template_engine.py ({vars}, **bold**, `code`, links, {#if})
                     └─ telegram_sender.py (send_message / edit_message_text, RetryAfter backoff)
                         └─ Telegram channel
```

- `store.py` persists `seen` dedupe keys, `msgmap`, and `positions` in SQLite.
- `owner_commands.py` handles `/id /template /showtemplate /preview /test /default` via `getUpdates` long-poll.

## Quickstart (local, no Telegram spam)

```bash
cp .env.example .env
# fill DHAN_CLIENT_ID, DHAN_ACCESS_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID
# keep DRY_RUN=true

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# run unit tests (42 tests, includes live-like send→edit flow)
python -m pytest -q

# dry-run loop (prints instead of posting)
python main.py
```

Set `DRY_RUN=false` only when ready for the live channel. Test with a 1-qty NSE_EQ order first.

## Configuration (.env)

See `.env.example` for all keys.

| Key | Purpose |
|---|---|
| `DHAN_CLIENT_ID`, `DHAN_ACCESS_TOKEN` | From web.dhan.co → My Profile → Access DhanHQ APIs |
| `DHAN_PIN`, `DHAN_TOTP_SECRET` | Optional — enables self-healing refresh after 24h expiry |
| `TELEGRAM_BOT_TOKEN` | From @BotFather `/newbot` |
| `TELEGRAM_CHANNEL_ID` | Channel ID like `-100123...` (add bot as Admin with Post+Edit) |
| `OWNER_ID` | Your Telegram user ID (DM bot `/id` to get it) — only this user may `/template` |
| `GROUP_WINDOW_SEC` | Symbol grouping window, default 120 |
| `ONLY_TRADED` | If true, new entries open only on TRADED (recommended) |
| `DRY_RUN` | `true` = print only, `false` = real posts |
| `CHART_URL` | Target for `[[numbers]]` blue links (no preview) |

## Template editing (no redeploy)

DM your bot:

- `/id` — get your user ID
- `/showtemplate` — see active template source
- `/template <text>` — or reply `/template` to a message — saves new template, validates placeholders, shows preview
- `/preview` — render sample with current template
- `/test` — post sample to channel (owner only)
- `/default` — restore built-in template

Placeholders: `{side} {symbol} {datetime} {entry} {sl} {t1} {t2} {risk} {reward} {reward1} {reward2} {rr} {rr1} {rr2} {exit} {url}`
Styling: `**bold**` → `<b>`, `` `code` `` → `<code>`, `[text](https://…)` → link, `> quote` → blockquote, `{#if var}…{#endif}`.

Saved to `data/template.txt` and hot-reloaded on next call.

Example default (RR-based):

```
PAPER TRADE
---------------------------
BUY NIFTY 24500 CE | 02:39 PM - 11 Sep 2024

Entry: 142.5
SL: 118
Target 1: 179.25  (Book Half)
Target 2: 191.5  (Book Other Half)
Lot Size: According to risk appetite
---------------------------
Risk: 24.5 points/lot
Reward: 36.75 to 49 points/lot
Risk-Reward: 1:1.5 to 1:2
---------------------------
TRADING THINGS X NIFTY33
> DISCLAIMER: WE ARE NOT SEBI REGISTERED ADVISOR...
```

## Testing

```bash
python -m pytest -q          # all tests
python replay_test.py --keep # live send→edit→delete in channel (requires real creds)
python local_send_test.py    # send one preview to channel from laptop
```

Key guarantees tested:
- Duplicate `order_no,status,qty` ignored
- Lone `PENDING` entry without fill → no message
- `TARGET LIMIT PENDING` → silent (RR wins), only `TRADED` exits count
- Late SL within 4h still edits same message
- Restart reloads `state.db` and edits original message
- Stale lone SL (>4h) does not create ghost SELL

## Deploy to Oracle (Always Free VM)

```bash
scp -r . ubuntu@<ORACLE_IP>:/opt/dhan-telegram
ssh ubuntu@<ORACLE_IP>

timedatectl set-timezone Asia/Kolkata
bash setup.sh                # venv + deps + dry-run selftest
nano .env                    # fill secrets, chmod 600 .env
sudo cp dhan-telegram.service /etc/systemd/system/
sudo systemctl enable --now dhan-telegram
sudo cp dhan-token-refresh.* /etc/systemd/system/
sudo systemctl enable --now dhan-token-refresh.timer

journalctl -u dhan-telegram -f          # watch SEND / EDIT lines
journalctl -u dhan-token-refresh -f     # token renew at 07:55 IST
```

No inbound ports (WS + Telegram are outbound 443). `Restart=always` + `data/state.db` survives reboots.

## Troubleshooting

- `WS error` or `token refresh failed` in journal → check Dhan token, `DHAN_CLIENT_ID`, network.
- `BadRequest: message is not modified` → harmless (content identical, now handled).
- `EDIT fallback SEND` log → original message was deleted, bot re-posted fresh (SL not lost).
- Oracle `Action Recommended` mail (idle reclaim) → SSH in within 7 days, `sudo systemctl restart dhan-telegram` and do activity; keep boot-volume backup.

## Disclaimer

For education only. Not SEBI registered. No investment advice. Trade at your own risk.

## License

MIT — see `LICENSE`.

## Acknowledgments

Built with `python-telegram-bot`, `websockets`, `dhanhq`, `python-dotenv`, `pyotp`. Thanks to the FOSS community — contributions welcome via issues and PRs.
