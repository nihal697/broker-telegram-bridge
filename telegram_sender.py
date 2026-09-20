"""Telegram sender — send new calls, edit same message when SL/target arrive.

Dry-run (default, DRY_RUN=true) prints instead of hitting network so tests
and Oracle trials never spam the channel. Real mode uses
python-telegram-bot Bot.send_message / edit_message_text with parse_mode=HTML
and RetryAfter backoff.
"""
from __future__ import annotations

import asyncio
import itertools


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        # Windows cp1252 console: fall back to ascii-safe
        print(text.encode("ascii", "backslashreplace").decode())


class TelegramSender:
    def __init__(self, bot_token: str = "", channel_id: str = "", dry_run: bool = True):
        self.bot_token = bot_token
        self.channel_id = channel_id
        self.dry_run = dry_run
        self._fake_ids = itertools.count(1000)
        self.sent: list[tuple[str, int | str]] = []  # (action, message_id) log for tests
        self._bot = None

    def _get_bot(self):
        if self._bot is None:
            from telegram import Bot

            if not self.bot_token:
                raise RuntimeError("TELEGRAM_BOT_TOKEN missing — set .env first")
            self._bot = Bot(token=self.bot_token)
        return self._bot

    async def send_call(self, html_text: str):
        """Send new call. Returns message_id (real or fake dry-run id)."""
        if self.dry_run:
            mid = next(self._fake_ids)
            _safe_print(f"[DRY-RUN send -> {self.channel_id or '@channel'} mid={mid}]\n{html_text}\n")
            self.sent.append(("send", mid))
            return mid
        from telegram.constants import ParseMode
        from telegram.error import BadRequest, Forbidden, RetryAfter, TimedOut, NetworkError

        bot = self._get_bot()
        for attempt in range(4):
            try:
                msg = await bot.send_message(
                    chat_id=self.channel_id, text=html_text, parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                self.sent.append(("send", msg.message_id))
                return msg.message_id
            except RetryAfter as e:
                await asyncio.sleep(int(getattr(e, "retry_after", 3)) + 1)
            except (BadRequest, Forbidden, TimedOut, NetworkError) as e:
                # BadRequest: bad HTML, chat not found, not admin etc — don't loop forever
                import logging as _lg
                _lg.getLogger("telegram_sender").error("send_message failed: %s", e)
                raise RuntimeError(f"send_message failed: {e}") from e
            except Exception as e:
                import logging as _lg
                _lg.getLogger("telegram_sender").error("send_message unexpected: %s", e)
                if attempt == 3:
                    raise
                await asyncio.sleep(2)
        raise RuntimeError("send_message failed after retries")

    async def edit_call(self, message_id, html_text: str) -> bool:
        """Edit existing call. Returns True on success."""
        if self.dry_run:
            _safe_print(f"[DRY-RUN edit mid={message_id}]\n{html_text}\n")
            self.sent.append(("edit", message_id))
            return True
        from telegram.constants import ParseMode
        from telegram.error import BadRequest, Forbidden, RetryAfter, TimedOut, NetworkError

        bot = self._get_bot()
        for _ in range(4):
            try:
                await bot.edit_message_text(
                    chat_id=self.channel_id, message_id=message_id,
                    text=html_text, parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                )
                self.sent.append(("edit", message_id))
                return True
            except RetryAfter as e:
                await asyncio.sleep(int(getattr(e, "retry_after", 3)) + 1)
            except BadRequest as e:
                msg = str(e).lower()
                if "message is not modified" in msg:
                    self.sent.append(("edit", message_id))
                    return True  # not an error — content identical
                if "message to edit not found" in msg or "message_id_invalid" in msg:
                    import logging as _lg
                    _lg.getLogger("telegram_sender").warning("edit_message not found mid=%s: %s", message_id, e)
                    return False  # caller may fallback to send
                import logging as _lg
                _lg.getLogger("telegram_sender").error("edit_message BadRequest: %s", e)
                return False
            except (Forbidden, TimedOut, NetworkError) as e:
                import logging as _lg
                _lg.getLogger("telegram_sender").warning("edit_message transient: %s", e)
                if _ == 3:
                    return False
                await asyncio.sleep(2)
            except Exception as e:
                import logging as _lg
                _lg.getLogger("telegram_sender").error("edit_message unexpected: %s", e)
                return False
        return False
