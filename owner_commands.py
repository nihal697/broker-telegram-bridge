"""Owner DM commands — edit the call template from Telegram itself.

Polls Bot.get_updates (alongside the Dhan WS loop, same asyncio process).
Only OWNER_ID may change anything; /id answers anyone (bootstrap helper).

Commands (DM the bot):
  /id                    reply with your user id (put it in .env as OWNER_ID)
  /settemplate <text...>  set template (alias: /template)
                         or reply /settemplate to a message containing it.
                         Validates placeholders, shows preview.
  /settemplate           (no args) -> bot asks you to send the template next;
                         your next message is saved as the template.
  /showtemplate          send back the active template source
  /preview               render a sample call with the active template (DM only)
  /test                  post a sample call to the channel (owner-only)

Template is persisted to data/template.txt (and kept in memory for speed).
Edits survive restarts/reboots — no need to /settemplate again.
Falls back to built-in DEFAULT_TEMPLATE if no file and no memory.
"""
from __future__ import annotations

import time
from pathlib import Path

from formatter import DEFAULT_TEMPLATE, Position, render_call
from template_engine import validate

# Persisted: file + in-memory cache. File is source of truth across restarts.
_mem_template: str | None = None

_TEMPLATE_PATH = Path(__file__).resolve().parent / "data" / "template.txt"


def _read_file_template() -> str | None:
    try:
        if _TEMPLATE_PATH.exists():
            txt = _TEMPLATE_PATH.read_text(encoding="utf-8")
            if txt.strip():
                return txt
    except Exception:
        pass
    return None

SAMPLE = Position(symbol="NIFTY 24500 CE", side="BUY", entry_price=142.5,
                   qty=50, entry_time="2026-09-19 09:30:02", sl=118,
                   exit_info="🔻SL hit @ 118")


PENDING_TTL_SEC = 300  # 5 minutes to send the template after /settemplate
PENDING_PREFIX = "pending_template:"


def load_template() -> str:
    """Active template: in-memory if set, else file, else built-in default."""
    if _mem_template is not None:
        return _mem_template
    file_tpl = _read_file_template()
    if file_tpl is not None:
        return file_tpl
    return DEFAULT_TEMPLATE


def save_template(text: str) -> None:
    global _mem_template
    _mem_template = text
    # persist to file so it survives restarts/reboots — no more re-sending after restart
    try:
        _TEMPLATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _TEMPLATE_PATH.write_text(text, encoding="utf-8")
    except Exception:
        pass
    # also load into memory for immediate use


# kept for test compatibility — clear memory + file
def reset_template() -> None:
    global _mem_template
    _mem_template = None
    try:
        if _TEMPLATE_PATH.exists():
            _TEMPLATE_PATH.unlink()
    except Exception:
        pass


def _pending_key(user_id) -> str:
    return f"{PENDING_PREFIX}{user_id}"


def _set_pending(store, user_id) -> None:
    try:
        store.set_scalar(_pending_key(user_id), str(time.time()))
    except Exception:
        pass


def _clear_pending(store, user_id) -> None:
    try:
        if hasattr(store, "db"):
            store.db.execute("DELETE FROM kv WHERE key=?", (_pending_key(user_id),))
            store.db.commit()
        else:
            store.set_scalar(_pending_key(user_id), "")
    except Exception:
        pass


def _is_pending(store, user_id) -> bool:
    if store is None:
        return False
    try:
        raw = store.get_scalar(_pending_key(user_id))
        if not raw:
            return False
        ts = float(raw)
        if time.time() - ts > PENDING_TTL_SEC:
            _clear_pending(store, user_id)
            return False
        return True
    except Exception:
        return False


def extract_command(text: str):
    """Split '/cmd args...' -> (cmd, args). Handles '@botname' suffix."""
    text = (text or "").strip()
    if not text.startswith("/"):
        return None, ""
    head, _, rest = text[1:].partition(" ")
    return head.split("@")[0].lower(), rest.strip()


def _markdown_from_entities(text: str, entities) -> str:
    """Reconstruct markdown from Telegram entities."""
    if not entities:
        return text or ""

    def _utf16_offset_to_str_idx(s: str, utf16_offset: int) -> int:
        units = 0
        for i, ch in enumerate(s):
            if units >= utf16_offset:
                return i
            units += 2 if ord(ch) > 0xFFFF else 1
        return len(s)

    def _slice(s: str, offset: int, length: int) -> str:
        start = _utf16_offset_to_str_idx(s, offset)
        end = _utf16_offset_to_str_idx(s, offset + length)
        return s[start:end]

    ents = sorted(entities, key=lambda e: (e.offset, -e.length))
    parts = []
    last_utf16 = 0
    for e in ents:
        t = getattr(e, "type", "")
        start = e.offset
        end = start + e.length
        if start < last_utf16:
            continue
        parts.append(_slice(text, last_utf16, start - last_utf16))
        inner = _slice(text, start, e.length)
        if t == "bot_command":
            parts.append(inner)
        elif t == "bold":
            parts.append(f"**{inner}**")
        elif t in ("italic", "underline", "strikethrough"):
            parts.append(f"**{inner}**")
        elif t == "code":
            parts.append(f"`{inner}`")
        elif t == "pre":
            lang = getattr(e, "language", "") or ""
            if lang:
                parts.append(f"```{lang}\n{inner}```")
            else:
                parts.append(f"`{inner}`")
        elif t == "text_link":
            url = getattr(e, "url", "") or ""
            parts.append(f"[{inner}]({url})")
        elif t == "blockquote":
            quoted = "\n".join(f"> {ln}" if ln else ">" for ln in inner.split("\n"))
            parts.append(quoted)
        else:
            parts.append(inner)
        last_utf16 = end
    total_units = sum(2 if ord(ch) > 0xFFFF else 1 for ch in text)
    parts.append(_slice(text, last_utf16, total_units - last_utf16))
    return "".join(parts)


def _template_from_message(msg) -> str:
    text = getattr(msg, "text", "") or getattr(msg, "caption", "") or ""
    entities = getattr(msg, "entities", None) or getattr(msg, "caption_entities", None) or []
    if text.lstrip().startswith("/"):
        cmd_end = text.find(" ")
        if cmd_end == -1:
            return ""
        tpl_text = text[cmd_end + 1 :]
        cmd_len = cmd_end + 1
        filtered = []
        for e in entities:
            if e.offset >= cmd_len:
                e2 = type(e)(offset=e.offset - cmd_len, length=e.length, type=e.type)
                for attr in ("url", "language"):
                    if hasattr(e, attr):
                        setattr(e2, attr, getattr(e, attr))
                filtered.append(e2)
            elif e.offset + e.length > cmd_len:
                continue
        return _markdown_from_entities(tpl_text, filtered)
    return _markdown_from_entities(text, entities)


async def handle_dm(bot, owner_id: str, chat_id, user_id, text: str,
                    reply_to_text: str = "", store=None) -> None:
    """Route one DM. Persisted to data/template.txt + in-memory cache."""
    cmd, args = extract_command(text)
    if cmd == "id":
        await bot.send_message(chat_id=chat_id,
                               text=f"user_id={user_id}\nchat_id={chat_id}")
        return
    allowed = {s.strip() for s in str(owner_id or "").split(",") if s.strip()}
    if str(user_id) not in allowed or not allowed:
        await bot.send_message(
            chat_id=chat_id,
            text="Owner only. Send /id and ask to set OWNER_ID.")
        return

    # Two-step flow: if user is in pending state and sends a non-command, treat it as template
    if cmd is None and _is_pending(store, user_id):
        new_tpl = text.strip()
        if not new_tpl:
            await bot.send_message(chat_id=chat_id, text="Empty message — send your template again or /settemplate to cancel.")
            return
        bad = validate(new_tpl)
        if bad:
            await bot.send_message(
                chat_id=chat_id,
                text=f"Unknown placeholders: {', '.join(bad)}. Not saved — fix and resend. You can still send the corrected template now (still pending).")
            return
        from config import load_settings as _ls
        try:
            probe = render_call(SAMPLE, new_tpl, _ls().chart_url)
            if probe.count("<b>") != probe.count("</b>") or probe.count("<code>") != probe.count("</code>"):
                raise ValueError("mismatched <b>/<code> tags — check ** and ` pairing")
        except Exception as e:
            await bot.send_message(chat_id=chat_id,
                                   text=f"Template looks broken: {e}\nNot saved — fix and resend. Still pending, send corrected template.")
            return
        save_template(new_tpl)
        _clear_pending(store, user_id)
        await bot.send_message(chat_id=chat_id, text="Template saved Preview:")
        from telegram.constants import ParseMode
        from telegram.error import BadRequest
        try:
            preview = render_call(SAMPLE, new_tpl, _ls().chart_url)
            await bot.send_message(chat_id=chat_id, text=preview,
                                   parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except BadRequest as e:
            await bot.send_message(chat_id=chat_id, text=f"Saved but HTML preview failed: {e}\nPlain preview:\n{render_call(SAMPLE, new_tpl, _ls().chart_url)}")
        except Exception as e:
            await bot.send_message(chat_id=chat_id, text=f"Saved but preview failed: {e}")
        return

    if cmd is not None and _is_pending(store, user_id):
        _clear_pending(store, user_id)

    async def _safe_preview(target_chat, preview_text: str, fallback_note: str = ""):
        from telegram.constants import ParseMode
        from telegram.error import BadRequest

        try:
            await bot.send_message(chat_id=target_chat, text=preview_text,
                                   parse_mode=ParseMode.HTML,
                                   disable_web_page_preview=True)
            return True
        except BadRequest as e:
            try:
                await bot.send_message(
                    chat_id=target_chat,
                    text=f"{fallback_note}\nHTML parse failed: {e}\n\nPlain preview:\n{preview_text}",
                )
            except Exception:
                pass
            return False
        except Exception as e:
            try:
                await bot.send_message(chat_id=target_chat,
                                       text=f"Preview failed: {e}")
            except Exception:
                pass
            return False

    if cmd == "showtemplate":
        await bot.send_message(chat_id=chat_id, text=load_template())
    elif cmd == "preview":
        from config import load_settings as _ls
        preview = render_call(SAMPLE, load_template(), _ls().chart_url)
        ok = await _safe_preview(chat_id, preview)
        if not ok:
            await bot.send_message(
                chat_id=chat_id,
                text="Tip: Check for unmatched ** or ` or [text](url) — preview fell back to plain text.",
            )
    elif cmd == "test":
        from config import load_settings as _ls
        s = _ls()
        if not s.telegram_channel_id:
            await bot.send_message(chat_id=chat_id, text="No TELEGRAM_CHANNEL_ID set")
            return
        preview = render_call(SAMPLE, load_template(), s.chart_url)
        from telegram.constants import ParseMode
        from telegram.error import BadRequest

        try:
            msg = await bot.send_message(chat_id=s.telegram_channel_id, text=preview,
                                         parse_mode=ParseMode.HTML,
                                         disable_web_page_preview=True)
            await bot.send_message(chat_id=chat_id,
                                   text=f"Posted preview to channel as mid={msg.message_id}")
        except BadRequest as e:
            await bot.send_message(chat_id=chat_id,
                                   text=f"Channel post failed — HTML parse error: {e}")
        except Exception as e:
            await bot.send_message(chat_id=chat_id, text=f"Channel post failed: {e}")
    elif cmd in ("settemplate", "template"):
        # /settemplate is primary, /template is alias — persistent to data/template.txt
        new_tpl = args or reply_to_text
        if not new_tpl:
            _set_pending(store, user_id)
            await bot.send_message(
                chat_id=chat_id,
                text="Got it — now just send your template as the next message (no /settemplate needed).\nPaste the full template with placeholders like {side} {entry} etc.\nYou have 5 minutes — send it now and I'll save + preview it.")
            return
        bad = validate(new_tpl)
        if bad:
            await bot.send_message(
                chat_id=chat_id,
                text=f"Unknown placeholders: {', '.join(bad)}. "
                     "Not saved — fix and resend.")
            return
        from config import load_settings as _ls
        try:
            probe = render_call(SAMPLE, new_tpl, _ls().chart_url)
            if probe.count("<b>") != probe.count("</b>") or probe.count("<code>") != probe.count("</code>"):
                raise ValueError("mismatched <b>/<code> tags — check ** and ` pairing")
        except Exception as e:
            await bot.send_message(chat_id=chat_id,
                                   text=f"Template looks broken: {e}\nNot saved — fix and resend.")
            return
        save_template(new_tpl)
        from config import load_settings as _ls2
        preview = render_call(SAMPLE, new_tpl, _ls2().chart_url)
        await bot.send_message(chat_id=chat_id, text="Template saved Preview:")
        await _safe_preview(chat_id, preview, fallback_note="Saved but HTML preview failed — channel posts may also fail.")
    else:
        await bot.send_message(
            chat_id=chat_id,
            text="Commands: /id /settemplate /showtemplate /preview /test")


async def poll_telegrams(bot, owner_id: str, store) -> None:
    """getUpdates long-poll loop. Runs forever; survives network blips."""
    import asyncio
    import logging

    log = logging.getLogger("tgcmd")
    offset = store.get_scalar("tg_offset") if hasattr(store, "get_scalar") else None
    try:
        offset = int(offset) if offset else None
    except (TypeError, ValueError):
        offset = None
    while True:
        try:
            updates = await bot.get_updates(offset=offset, timeout=30,
                                            allowed_updates=["message"])
            for u in updates:
                offset = u.update_id + 1
                try:
                    store.set_scalar("tg_offset", str(offset))
                except Exception:
                    pass
                msg = getattr(u, "message", None)
                if not msg or not (getattr(msg, "text", "") or getattr(msg, "caption", "")):
                    continue
                full_text = getattr(msg, "text", "") or getattr(msg, "caption", "") or ""
                full_entities = getattr(msg, "entities", None) or getattr(msg, "caption_entities", None) or []
                full_md = _markdown_from_entities(full_text, full_entities)
                reply = getattr(msg, "reply_to_message", None)
                reply_md = ""
                if reply is not None:
                    r_text = getattr(reply, "text", "") or getattr(reply, "caption", "") or ""
                    r_ents = getattr(reply, "entities", None) or getattr(reply, "caption_entities", None) or []
                    reply_md = _markdown_from_entities(r_text, r_ents)
                try:
                    await handle_dm(bot, owner_id, msg.chat_id,
                                    msg.from_user.id, full_md, reply_md, store)
                except Exception as e:
                    log.warning("dm handling failed: %s", e)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("getUpdates failed: %s", e)
            await asyncio.sleep(5)
