"""Slice 4 tests — end-to-end dry-run: entry SEND, SL edit, target edit, no dupes."""
import asyncio
import os
import tempfile
from config import Settings
from main import Bridge
from telegram_sender import TelegramSender
from store import Store


def make_bridge():
    tmp = tempfile.mkdtemp()
    s = Settings(telegram_channel_id="@test", dry_run=True,
                 db_path=os.path.join(tmp, "s.db"), only_traded=True)
    sender = TelegramSender(channel_id="@test", dry_run=True)
    return Bridge(settings=s, sender=sender, store=Store(s.db_path))


def test_e2e_send_then_edits():
    b = make_bridge()
    r1 = asyncio.run(b.handle_event({"Symbol": "NIFTY 24500 CE", "TxnType": "B",
                                     "TradedPrice": 142.5, "Status": "TRADED",
                                     "OrderNo": "E1", "Quantity": 50,
                                     "OrderDateTime": "2024-09-11 10:16:02"}))
    assert r1[0] == "send"
    r2 = asyncio.run(b.handle_event({"Symbol": "NIFTY 24500 CE", "TxnType": "S",
                                     "TriggerPrice": 118, "OrderType": "STOP_LOSS_MARKET",
                                     "Status": "PENDING", "OrderNo": "SL1"}))
    assert r2[0] == "edit"
    # target order placed but unfilled: nothing new to show
    r3 = asyncio.run(b.handle_event({"Symbol": "NIFTY 24500 CE", "TxnType": "S",
                                     "Price": 165, "OrderType": "LIMIT",
                                     "Status": "PENDING", "OrderNo": "T1"}))
    assert r3 is None
    # SL fills -> SL-hit label on same message
    r4 = asyncio.run(b.handle_event({"Symbol": "NIFTY 24500 CE", "TxnType": "S",
                                     "TradedPrice": 118, "OrderType": "STOP_LOSS_MARKET",
                                     "Status": "TRADED", "OrderNo": "SL1"}))
    assert r4[0] == "edit"
    # duplicate redelivery ignored
    r5 = asyncio.run(b.handle_event({"Symbol": "NIFTY 24500 CE", "TxnType": "S",
                                     "TradedPrice": 118, "OrderType": "STOP_LOSS_MARKET",
                                     "Status": "TRADED", "OrderNo": "SL1"}))
    assert r5 is None
    # lone PENDING entry (no fill) ignored — no spam
    r6 = asyncio.run(b.handle_event({"Symbol": "BANKNIFTY", "TxnType": "B",
                                     "Price": 500, "Status": "PENDING", "OrderNo": "E9"}))
    assert r6 is None


def test_restart_recovers_msgmap():
    import tempfile
    from main import Bridge
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "s.db")
    s = Settings(telegram_channel_id="@test", dry_run=True, db_path=db, only_traded=True)
    b = Bridge(settings=s, sender=TelegramSender(channel_id="@test", dry_run=True), store=Store(db))
    asyncio.run(b.handle_event({"Symbol": "X", "TxnType": "B", "TradedPrice": 10,
                                "Status": "TRADED", "OrderNo": "E1"}))
    # simulate restart: brand-new Bridge on SAME db -> position restored -> edit
    b2 = Bridge(settings=s, sender=TelegramSender(channel_id="@test", dry_run=True), store=Store(db))
    r = asyncio.run(b2.handle_event({"Symbol": "X", "TxnType": "S", "TriggerPrice": 9,
                                     "OrderType": "STOP_LOSS_MARKET",
                                     "Status": "PENDING", "OrderNo": "SL1"}))
    assert r[0] == "edit", r
