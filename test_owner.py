"""Owner command tests — routing, gating, template save/validate (fake bot)."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import owner_commands as oc


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id=None, text=None, **kwargs):
        self.sent.append(text)
        return None


def run(coro):
    return asyncio.run(coro)


def test_id_answers_anyone():
    b = FakeBot()
    run(oc.handle_dm(b, "", 111, 222, "/id"))
    assert b.sent == ["user_id=222\nchat_id=111"]


def test_stranger_blocked():
    b = FakeBot()
    run(oc.handle_dm(b, "999", 111, 222, "/test"))
    assert "Owner only" in b.sent[0]


def test_owner_test_renders_sample():
    import os as _os
    _os.environ["TELEGRAM_CHANNEL_ID"] = _os.getenv("TELEGRAM_CHANNEL_ID") or "-100test"
    b = FakeBot()
    # FakeBot needs to mimic channel send — handle_dm calls bot.send_message for channel too
    orig_send = b.send_message

    async def _fake_send(chat_id=None, text=None, **kwargs):
        # record and return object with message_id for /test path
        b.sent.append(text)
        class _M:
            message_id = 999
        return _M()

    b.send_message = _fake_send
    run(oc.handle_dm(b, "222", 111, 222, "/test"))
    assert any("PAPER TRADE" in s and "179.25" in s for s in b.sent)


def test_template_save_validate_and_show(tmp_path=None):
    import tempfile
    from pathlib import Path
    oc.TEMPLATE_PATH = Path(tempfile.mkdtemp()) / "template.txt"
    b = FakeBot()
    run(oc.handle_dm(b, "222", 111, 222, "/template **{side}** {bogus}"))
    assert "Unknown placeholders: bogus" in b.sent[0]
    assert not oc.TEMPLATE_PATH.exists()
    run(oc.handle_dm(b, "222", 111, 222, "/template **{side}** `{entry}`"))
    assert "Template saved" in b.sent[1]
    assert oc.load_template() == "**{side}** `{entry}`"
    run(oc.handle_dm(b, "222", 111, 222, "/showtemplate"))
    assert b.sent[-1] == "**{side}** `{entry}`"
    run(oc.handle_dm(b, "222", 111, 222, "/default"))
    assert oc.load_template() != "**{side}** `{entry}`"
