"""Slice 3 tests — dry-run never touches network."""
import asyncio
from telegram_sender import TelegramSender


def test_send_then_edit_dry_run():
    s = TelegramSender(channel_id="@test", dry_run=True)
    mid = asyncio.run(s.send_call("<b>BUY</b> Entry 10"))
    assert isinstance(mid, int)
    ok = asyncio.run(s.edit_call(mid, "<b>BUY</b> Entry 10 SL 9"))
    assert ok is True
    assert s.sent == [("send", mid), ("edit", mid)]
