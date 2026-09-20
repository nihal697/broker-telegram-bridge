"""Owner DM commands — edit the call template from Telegram itself.

Polls Bot.get_updates (alongside the Dhan WS loop, same asyncio process).
Only OWNER_ID may change anything; /id answers anyone (bootstrap helper).

Commands (DM the bot):
  /id                    reply with your user id (put it in .env as OWNER_ID)
  /template <text...>    save new template (or reply /template to a message
                         containing it). Validates placeholders, shows preview.
  /template              (no args) → bot asks you to send the template next;
                         your next message is saved as the template.
  /showtemplate          send back the active template source
  /preview               render a sample call with the active template (DM only)
  /test                  post a sample call to the channel (owner-only)
  /default               restore the built-in template

Template is stored at data/template.txt and hot-reloaded on every render —
edits apply to the NEXT call without restarts.
"""
from __future__ import annotations

import time
from pathlib import Path

from formatter import DEFAULT_TEMPLATE, Position, render_call
from template_engine import validate

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = BASE_DIR / "data" / "template.txt"

SAMPLE = Position(symbol="NIFTY 24500 CE", side="BUY", entry_price=142.5,
                   qty=50, entry_time="2026-09-19 09:30:02", sl=118,
                   exit_info="🔻SL hit @ 118")


PENDING_TTL_SEC = 300  # 5 minutes to send the template after /template
PENDING_PREFIX = "pending_template:"


def load_template() -> str:
    """Active template: owner's file if present, else built-in default."""
    try:
        if TEMPLATE_PATH.exists():
            return TEMPLATE_PATH.read_text(encoding="utf-8")
    except OSError:
        pass
    return DEFAULT_TEMPLATE


def save_template(text: str) -> None:
    TEMPLATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEMPLATE_PATH.write_text(text, encoding="utf-8")


def reset_template() -> None:
    try:
        TEMPLATE_PATH.unlink()
    except OSError:
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
        # kv table has no delete helper — just clear by setting empty and let TTL handle it,
        # or directly delete via db if available
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
    """Reconstruct markdown from Telegram entities.

    Converts Telegram's entity-annotated plain text back to our template
    markdown: bold -> **, code -> `, pre -> ```, text_link -> [text](url),
    blockquote -> > line. Plain ** etc typed literally stays as-is (no entities).
    Handles UTF-16 offsets (Telegram) vs Python Unicode correctly (emoji = 2 units).
    """
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

    # sort by offset, longest first for same offset (to handle nesting)
    ents = sorted(entities, key=lambda e: (e.offset, -e.length))
    # Build markdown by walking text and inserting markers.
    # We need to handle entities in order, but offsets are in UTF-16, so we
    # convert to str indices for slicing.
    parts = []
    last_utf16 = 0
    # For mapping, we need to track last position in terms of UTF-16 offset,
    # but we also need to know corresponding str index. Instead, walk through
    # entities sorted and keep last end in UTF-16, and slice text via helper.
    for e in ents:
        t = getattr(e, "type", "")
        start = e.offset
        end = start + e.length
        if start < last_utf16:
            continue  # overlapping, skip inner
        # text between last and start
        parts.append(_slice(text, last_utf16, start - last_utf16))
        inner = _slice(text, start, e.length)
        if t == "bot_command":
            # keep command text as-is for extract_command to parse
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
    # tail
    # remaining text from last_utf16 to end
    # compute total UTF-16 length
    total_units = sum(2 if ord(ch) > 0xFFFF else 1 for ch in text)
    parts.append(_slice(text, last_utf16, total_units - last_utf16))
    return "".join(parts)


def _template_from_message(msg) -> str:
    """Extract template markdown from a message, handling both plain markdown and styled entities."""
    text = getattr(msg, "text", "") or getattr(msg, "caption", "") or ""
    entities = getattr(msg, "entities", None) or getattr(msg, "caption_entities", None) or []
    # If message is a /template command, strip the command prefix and keep entities-adjusted slice
    if text.lstrip().startswith("/"):
        cmd_end = text.find(" ")
        if cmd_end == -1:
            return ""  # no template part
        # Template part is after first space
        tpl_text = text[cmd_end + 1 :]
        # Filter entities to those within tpl_text
        cmd_len = cmd_end + 1
        filtered = []
        for e in entities:
            if e.offset >= cmd_len:
                # shift offset
                e2 = type(e)(offset=e.offset - cmd_len, length=e.length, type=e.type)
                # copy url/language if present
                for attr in ("url", "language"):
                    if hasattr(e, attr):
                        setattr(e2, attr, getattr(e, attr))
                filtered.append(e2)
            elif e.offset + e.length > cmd_len:
                # entity straddles command and template (unlikely)
                continue
        return _markdown_from_entities(tpl_text, filtered)
    return _markdown_from_entities(text, entities)


async def handle_dm(bot, owner_id: str, chat_id, user_id, text: str,
                    reply_to_text: str = "", store=None) -> None:
    """Route one DM. Pure logic except bot.send_message calls.

    Note: when called from poll_telegrams, text/reply_to_text are already
    reconstructed markdown (entities handled). Direct callers may pass plain text.
    Supports two-step /template flow: /template → bot asks for template → next
    message from same user is saved as template.
    """
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
            await bot.send_message(chat_id=chat_id, text="Empty message — send your template again or /template to cancel.")
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
        await bot.send_message(chat_id=chat_id, text="Template saved \u2705 Preview:")
        # preview with safe fallback
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

    # If user sends another command while pending, clear pending and handle new command normally
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
            # HTML parse failed — send plain fallback + error details so user isn't left hanging
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
    elif cmd == "default":
        reset_template()
        await bot.send_message(chat_id=chat_id,
                               text="Built-in template restored.")
        # also show preview of default so friend sees it immediately
        from config import load_settings as _ls
        preview = render_call(SAMPLE, load_template(), _ls().chart_url)
        await _safe_preview(chat_id, preview)
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
        # post preview directly to the channel (owner-only)
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
    elif cmd == "template":
        new_tpl = args or reply_to_text
        if not new_tpl:
            _set_pending(store, user_id)
            await bot.send_message(
                chat_id=chat_id,
                text="Got it — now just send your template as the next message (no /template needed).\nPaste the full template with placeholders like {side} {entry} etc.\nYou have 5 minutes — send it now and I'll save + preview it.")
            return
        bad = validate(new_tpl)
        if bad:
            await bot.send_message(
                chat_id=chat_id,
                text=f"Unknown placeholders: {', '.join(bad)}. "
                     "Not saved — fix and resend.")
            return
        # Validate HTML by rendering sample before committing
        from config import load_settings as _ls
        try:
            probe = render_call(SAMPLE, new_tpl, _ls().chart_url)
            # quick tag-balance check: if preview would fail, warn now
            # (we don't send yet, just ensure it renders without exception)
            if probe.count("<b>") != probe.count("</b>") or probe.count("<code>") != probe.count("</code>"):
                raise ValueError("mismatched <b>/<code> tags — check ** and ` pairing")
        except Exception as e:
            await bot.send_message(chat_id=chat_id,
                                   text=f"Template looks broken: {e}\nNot saved — fix and resend.")
            return
        save_template(new_tpl)
        from config import load_settings as _ls2
        preview = render_call(SAMPLE, new_tpl, _ls2().chart_url)
        await bot.send_message(chat_id=chat_id, text="Template saved \u2705 Preview:")
        await _safe_preview(chat_id, preview, fallback_note="Saved but HTML preview failed — channel posts may also fail.")
    else:
        await bot.send_message(
            chat_id=chat_id,
            text="Commands: /id /template /showtemplate /test /preview /default")


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
