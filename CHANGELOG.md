# Changelog

All notable changes to this project will be documented in this file.
The format is based on Keep a Changelog and Semantic Versioning.

## [1.0.1] - 2026-09-20

Broker-agnostic positioning — same core, now documented for any broker.

- README generalized: core is broker-free, Dhan is reference adapter.
- Add `docs/BROKERS.md` (canonical dict, Angel/Zerodha/webhook examples).
- Repo renamed `dhan-telegram-bridge` → `broker-telegram-bridge` (redirect preserved).
- No code change to live path, 42/42 tests still pass.

## [1.0.0] - 2026-09-20

First public release — hardened live path verified with real Telegram messages.

### Added
- Live Order Update WS bridge (`dhan_ws.py`) with `MsgCode 42` auth and exponential backoff reconnect.
- Position tracker (`grouper.py`) — one open slot per `symbol|side`, SL/target grouping via `AlgoOrdNo`/symbol window, 4h late-SL window, remarks `SL:` fallback.
- Formatter (`formatter.py`) with RR-computed targets `T1 1.5R / T2 2R` (direction-aware) and `{#if}` mini-template engine.
- Telegram sender (`telegram_sender.py`) with dry-run, `RetryAfter` backoff, `BadRequest`/`MessageNotModified` handling.
- Owner DM commands (`owner_commands.py`): `/id /template /showtemplate /preview /test /default`, hot-reloaded `data/template.txt`.
- SQLite store (`store.py`) for dedupe, `msgmap`, positions.
- Daily token refresh (`auth_refresh.py` + `dhan-token-refresh.service/.timer`) via `RenewToken`/TOTP.
- Oracle `systemd` units (`dhan-telegram.service`) and `setup.sh`.
- Full test suite (42 tests) covering dedupe, silent target-pending, late SL, restart recovery, stale-SL ghost guard.
- Scripts: `local_send_test.py`, `replay_test.py`.

### Fixed
- Template conditional for empty `datetime` — no stray `|` when datetime missing.
- Telegram sender now handles `BadRequest`/`Forbidden`/`TimedOut` and `message is not modified` as success.
- Bridge `EDIT` now falls back to fresh `SEND` if original message was deleted (SL not lost).
- Stale lone `STOP_LOSS_LEG PENDING` after >4h no longer creates spurious SELL.

### Security
- `.env` is gitignored. `.env.example` contains only placeholders. No tokens committed.

[1.0.1]: https://github.com/nihal697/broker-telegram-bridge/releases/tag/v1.0.1
[1.0.0]: https://github.com/nihal697/broker-telegram-bridge/releases/tag/v1.0.0
