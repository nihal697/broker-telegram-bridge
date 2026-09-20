"""Main loop — WS -> tracker -> formatter -> Telegram (send then edit).

Event policy (approved):
- New entry opens ONLY on TRADED/PART_TRADED when ONLY_TRADED=true (no PENDING spam).
- Edits (SL/target PENDING, modifies, CANCELLED, exits) always processed.
- Duplicates by (order_no, status, qty-or-price) ignored via SQLite.
"""
from __future__ import annotations

import asyncio
import json
import logging

from config import load_settings
from formatter import render_call
from grouper import PositionTracker, normalize
from owner_commands import load_template, poll_telegrams
from store import Store
from telegram_sender import TelegramSender

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("main")


class Bridge:
    def __init__(self, settings=None, sender=None, store=None):
        self.s = settings or load_settings()
        self.tracker = PositionTracker(window_sec=self.s.group_window_sec)
        self.sender = sender or TelegramSender(
            self.s.telegram_bot_token, self.s.telegram_channel_id, self.s.dry_run)
        self.store = store or Store(self.s.db_path)
        self._restore_positions()

    def _restore_positions(self):
        import json as _json

        from formatter import Position as _Pos

        try:
            for key, blob in self.store.load_positions().items():
                try:
                    self.tracker.restore(key, _Pos.from_dict(_json.loads(blob)))
                except Exception as e:
                    log.warning("restore %s failed: %s", key, e)
        except Exception as e:
            log.warning("position restore failed: %s", e)

    async def handle_event(self, update: dict):
        ev = normalize(update)
        if self.s.only_traded and ev["status"] not in (
                "TRADED", "PART_TRADED", "PENDING", "TRANSIT",
                "CANCELLED", "REJECTED", "EXPIRED"):
            return None
        dup_key_qty = str(ev["qty"] or ev["price"] or "")
        if ev["order_no"] and self.store.is_duplicate(ev["order_no"], ev["status"], dup_key_qty):
            return None
        # gate NEW entries to TRADED when only_traded (edits still flow)
        if self.s.only_traded and ev["status"] in ("PENDING", "TRANSIT"):
            # allow if it resolves to an edit on an existing slot
            probe = self.tracker._find_slot(ev)
            if probe is None or probe.closed:
                # lone PENDING with no open slot: could be SL/target pre-entry?
                # still allow tracker to decide; it will open a slot — but we
                # downgrade lone PENDING entries to ignore to avoid spam.
                if not self.tracker._is_sl(ev) and not self.tracker._is_target(ev):
                    return None
        result = self.tracker.handle(update)
        if not result:
            return None
        action, pos = result
        html_text = render_call(pos, load_template(), self.s.chart_url)
        key = f"{pos.symbol}|{pos.side}"
        if action == "send":
            mid = await self.sender.send_call(html_text)
            self.store.save_msg(key, mid)
            self.store.save_pos(key, json.dumps(pos.to_dict()))
            log.info("SEND %s mid=%s", key, mid)
            return ("send", mid)
        mid = self.store.get_msg(key)
        if mid is None:
            # restart lost map: send fresh instead of dropping the edit
            try:
                mid = await self.sender.send_call(html_text)
            except Exception as e:
                log.error("SEND (recovered) failed %s: %s", key, e)
                return None
            self.store.save_msg(key, mid)
            log.info("SEND (recovered) %s mid=%s", key, mid)
            return ("send", mid)
        try:
            ok = await self.sender.edit_call(mid, html_text)
        except Exception as e:
            log.error("EDIT failed %s mid=%s: %s", key, mid, e)
            return None
        if not ok:
            # edit failed (message deleted / not found) -> fallback to fresh send so SL is not lost
            try:
                new_mid = await self.sender.send_call(html_text)
                self.store.save_msg(key, new_mid)
                log.warning("EDIT fallback SEND %s old_mid=%s new_mid=%s", key, mid, new_mid)
                self.store.save_pos(key, json.dumps(pos.to_dict()))
                return ("send", new_mid)
            except Exception as e:
                log.error("EDIT fallback SEND failed %s: %s", key, e)
                return None
        self.store.save_pos(key, json.dumps(pos.to_dict()))
        log.info("EDIT %s mid=%s", key, mid)
        return ("edit", mid)


async def _amain():
    from dhan_ws import run_forever

    s = load_settings()
    if not s.dhan_client_id:
        raise SystemExit("DHAN_CLIENT_ID missing — copy .env.example to .env first")
    bridge = Bridge(s)

    def current_token():
        # re-read .env (auth_refresh.py rewrites it daily)
        return load_settings().dhan_access_token or s.dhan_access_token

    async def _commands():
        if not s.telegram_bot_token:
            return
        from telegram import Bot
        await poll_telegrams(Bot(token=s.telegram_bot_token), s.owner_id,
                             bridge.store)

    await asyncio.gather(
        run_forever(s.order_ws_url, s.dhan_client_id,
                    s.dhan_access_token, bridge.handle_event, current_token),
        _commands(),
    )


def main():
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
