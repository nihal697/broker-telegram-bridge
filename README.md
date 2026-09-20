# Broker to Telegram Bridge

Post every manual trade you take on your broker to your Telegram channel. Entry is sent instantly, and the **same message is edited** when the stop-loss is placed or hit. Targets are computed from risk-reward, not from pending limit orders.

Broker-agnostic core — first adapter is **Dhan**, but any broker that can emit order updates (WebSocket or webhook) works via the same `normalize()` adapter. Built for Indian retail traders who run a Telegram community and want zero manual copy-paste.

## How it works

```
Any Broker (Dhan, Angel One, Zerodha, etc.)
 └─ Order Update Source (WS / webhook)
     └─ broker_adapter.py  (normalize raw order → canonical dict)
         └─ main.py (dedupe → PositionTracker → formatter)
             └─ grouper.py (one open slot per symbol|side, 4h late-SL window)
                 └─ formatter.py + template_engine.py ({vars}, **bold**, `code`, links, {#if})
                     └─ telegram_sender.py (send_message / edit_message_text)
                         └─ Telegram channel
```

Core is broker-agnostic: `grouper`, `formatter`, `telegram_sender`, `store`, `template_engine`, and `owner_commands` know nothing about Dhan. Only the adapter (`dhan_ws.py` / `dhan-*` services) is Dhan-specific.

## Features

- **Instant entry** on `TRADED` / `PART_TRADED`. Pending entries are not spammed.
- **Same-message edits** when SL arrives (`STOP_LOSS_MARKET` with `TriggerPrice`) or when SL is hit.
- **RR-computed targets**: `T1 = 1.5R`, `T2 = 2R` (direction-aware, handles BUY/SELL). No dependency on limit prices.
- **Super Order / BO support** via `AlgoOrdNo` linking when your broker provides it.
- **Normal order grouping** via symbol + side + time window (default 120s, extended to 4h for late SL).
- **Deduplication** via `data/state.db` (`order_no, status, qty`). Restarts still edit the same Telegram message ID.
- **Telegram-editable template** — DM the bot `/template` to change layout without redeploy. Hot-reloaded, validation for unknown placeholders.
- **Dry-run mode** (`DRY_RUN=true` prints to console instead of hitting Telegram) for safe local testing.
- **Oracle-ready**: `systemd` services + daily token refresh timer, no inbound ports.

## Supported brokers

| Broker | Adapter | Status | Notes |
|---|---|---|---|
| **Dhan** | `dhan_ws.py` + `dhan-telegram.service` | Stable | Live Order Update WS `wss://api-order-update.dhan.co` (MsgCode 42). Includes `RenewToken` timer. |
| **Angel One** | `brokers/angel.py` (stub) | Roadmap | SmartAPI order WS → `normalize()` (TxnType, OrderNo, TriggerPrice). Contribute if you use Angel. |
| **Zerodha Kite** | `brokers/kite.py` (stub) | Roadmap | Kite Connect `order_update` WS → same canonical shape. |
| **Generic webhook** | `brokers/webhook.py` | Available | POST any JSON with `symbol, side, price, triggerPrice, status, orderId` to `main.handle_event()` — no broker SDK needed. |
| **Any other** | Add `brokers/<name>.py` | Easy | Implement `normalize()` + `run_forever(broker, on_message)` — see `docs/BROKERS.md`. |

If your broker exposes order updates via WebSocket or webhook, the bridge works. Dhan is the reference; the core is already broker-free.

## Quickstart (local, no Telegram spam)

```bash
cp .env.example .env
# choose BROKER=dhan (default) and fill BROKER_CLIENT_ID, BROKER_ACCESS_TOKEN,
# TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID
# keep DRY_RUN=true

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

python -m pytest -q        # 42 tests, includes live-like send→edit flow
python main.py             # dry-run loop (prints instead of posting)
```

Set `DRY_RUN=false` only when ready for the live channel. Test with a 1-qty NSE_EQ order first.

## Configuration (.env)

See `.env.example` for all keys. `DHAN_*` vars still work for backward compatibility; new keys are `BROKER_*`.

| Key | Purpose |
|---|---|
| `BROKER` | `dhan` (default), `angel`, `kite`, `generic` |
| `BROKER_CLIENT_ID`, `BROKER_ACCESS_TOKEN` | Your broker API credentials |
| `DHAN_CLIENT_ID`, `DHAN_ACCESS_TOKEN` | Alias for `dhan` (legacy) |
| `DHAN_PIN`, `DHAN_TOTP_SECRET` | Optional — Dhan self-healing refresh after 24h expiry |
| `TELEGRAM_BOT_TOKEN` | From @BotFather `/newbot` |
| `TELEGRAM_CHANNEL_ID` | Channel ID like `-100123...` (add bot as Admin with Post+Edit) |
| `OWNER_ID` | Your Telegram user ID (DM bot `/id` to get it) — only this user may `/template` |
| `GROUP_WINDOW_SEC` | Symbol grouping window, default 120 |
| `ONLY_TRADED` | If true, new entries open only on TRADED (recommended) |
| `DRY_RUN` | `true` = print only, `false` = real posts |
| `CHART_URL` | Target for `[[numbers]]` blue links (no preview) |

Adapter-specific vars are namespaced, e.g. `ANGEL_API_KEY`, `KITE_API_KEY`. See `docs/BROKERS.md`.

## Adding a new broker (5 minutes)

1. Create `brokers/<broker>.py` with:
   ```python
   def normalize(raw: dict) -> dict:  # map to canonical: symbol, side, price, trigger, status, order_no, algo, qty, ...
   async def run_forever(on_message, get_token=None): # connect, auth, call on_message(update) per order
   ```
2. Wire `BROKER=<name>` in `.env` and add `elif broker == "<name>"` in `main.py`’s `_amain()`.
3. Keep core untouched — `grouper.py`/`formatter.py`/`telegram_sender.py` already handle any broker shape.

See `docs/BROKERS.md` for canonical dict spec and examples for Angel/Zerodha.

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

Works the same for any broker — just change `BROKER=` in `.env`.

```bash
scp -r . ubuntu@<ORACLE_IP>:/opt/dhan-telegram   # or /opt/broker-telegram
ssh ubuntu@<ORACLE_IP>

timedatectl set-timezone Asia/Kolkata
bash setup.sh                # venv + deps + dry-run selftest
nano .env                    # fill secrets, chmod 600 .env
sudo cp dhan-telegram.service /etc/systemd/system/  # rename to broker-telegram.service if generic
sudo systemctl enable --now dhan-telegram
sudo cp dhan-token-refresh.* /etc/systemd/system/   # Dhan-only; skip for other brokers
sudo systemctl enable --now dhan-token-refresh.timer

journalctl -u dhan-telegram -f          # watch SEND / EDIT lines
```

No inbound ports (broker WS + Telegram are outbound 443). `Restart=always` + `data/state.db` survives reboots.

## Troubleshooting

- `WS error` or `token refresh failed` in journal → check broker token, `BROKER_CLIENT_ID`, network.
- `BadRequest: message is not modified` → harmless (content identical, now handled).
- `EDIT fallback SEND` log → original message was deleted, bot re-posted fresh (SL not lost).
- Oracle `Action Recommended` mail (idle reclaim) → SSH in within 7 days, `sudo systemctl restart dhan-telegram` and do activity; keep boot-volume backup.

## Disclaimer

For education only. Not SEBI registered. No investment advice. Trade at your own risk.

## License

MIT — see `LICENSE`.

## Acknowledgments

Built with `python-telegram-bot`, `websockets`, `python-dotenv`. Broker adapters use each broker’s official SDK (`dhanhq`, `smartapi-python`, `kiteconnect`). Thanks to the FOSS community — contributions welcome via issues and PRs.
