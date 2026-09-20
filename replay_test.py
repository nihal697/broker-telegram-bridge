"""Replay test — feed synthetic Dhan order updates through the REAL pipeline
(tracker -> formatter -> live Telegram send/edit), then delete the messages.

Places NO orders. Run explicitly only:
    ./venv/bin/python replay_test.py [--keep]

--keep leaves the final message in the channel for visual inspection.
Default deletes everything after proving send+edit works.

Scenario mirrors the approved flow: entry fill -> SL placed -> SL fills.
Targets are RR-computed (1:1.5 / 1:2); target-hit labels are manual by design.
"""
import asyncio
import sys

sys.path.insert(0, "/opt/dhan-telegram")

from config import load_settings
from main import Bridge
from telegram_sender import TelegramSender
from store import Store
import tempfile
import os

SCENARIO = [
    # entry fills -> SEND immediately with placeholders + datetime
    {"Symbol": "REPLAYTEST NIFTY 24500 CE", "TxnType": "B", "TradedPrice": 142.5,
     "Status": "TRADED", "OrderNo": "REPLAY-E1", "Quantity": 50,
     "Product": "I", "OrderDateTime": "2026-09-19 15:30:02"},
    # SL placed -> EDIT adds SL + computed T1/T2 + risk/reward
    {"Symbol": "REPLAYTEST NIFTY 24500 CE", "TxnType": "S", "TriggerPrice": 118,
     "OrderType": "STOP_LOSS_MARKET", "Status": "PENDING", "OrderNo": "REPLAY-SL1"},
    # SL fills -> EDIT labels SL hit
    {"Symbol": "REPLAYTEST NIFTY 24500 CE", "TxnType": "S", "TradedPrice": 118,
     "OrderType": "STOP_LOSS_MARKET", "Status": "TRADED", "OrderNo": "REPLAY-SL1",
     "Quantity": 50},
]


async def main():
    keep = "--keep" in sys.argv
    s = load_settings()
    tmp = tempfile.mkdtemp()
    sender = TelegramSender(s.telegram_bot_token, s.telegram_channel_id,
                            dry_run=False)  # REAL sends, test channel content
    bridge = Bridge(settings=s, sender=sender,
                    store=Store(os.path.join(tmp, "replay.db")))
    mids = []
    for ev in SCENARIO:
        res = await bridge.handle_event(ev)
        print("EVENT", ev["OrderNo"], ev["Status"], "->", res)
        if res:
            mids.append(res[1])
        await asyncio.sleep(2)
    uniq = sorted(set(mids))
    print("MESSAGE IDS (must all be equal):", uniq)
    assert len(uniq) == 1, "send-then-edit broken: more than one message!"
    if not keep:
        from telegram import Bot
        bot = Bot(token=s.telegram_bot_token)
        await bot.delete_message(chat_id=s.telegram_channel_id,
                                 message_id=uniq[0])
        print("DELETED test message — REPLAY PASS")
    else:
        print("KEPT test message for inspection — REPLAY PASS")


if __name__ == "__main__":
    asyncio.run(main())
