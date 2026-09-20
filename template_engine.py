"""Mini template engine for Telegram-editable call templates.

The owner edits the template by DMing the bot (/template) — no code deploys.
Syntax (Telegram-friendly, a subset of Markdown):
  {name}            placeholder (escaped once at render, never double)
  **bold**          -> <b>bold</b>
  `code`            -> <code>code</code>   (red mono, theme-dependent)
  [[text]]          -> <a href="{url}">text</a>  (blue via text_link; tappable)
  [text](https://…) -> <a href="…">text</a>
  > quote           whole line -> <blockquote>quote</blockquote>
  {#if var}…{#endif} include block only if var is truthy (flat, non-nested)

Order of operations: conditionals -> placeholders (raw) -> per line: escape
once -> inline markup -> quote wrap. Single escaping pass means values can
never double-escape; unknown placeholders stay visible as {name} so typos
are obvious in preview.
"""
from __future__ import annotations

import html
import re

_IF_RE = re.compile(r"\{#if (\w+)\}(.*?)\{#endif\}", re.DOTALL)
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BLUE_RE = re.compile(r"\[\[([^\]]+)\]\]")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_CODE_RE = re.compile(r"`([^`\n]+)`")


def render(template: str, values: dict) -> str:
    text = _apply_conditionals(template, values)
    text = _apply_placeholders(text, values)
    url = str(values.get("url") or "").strip()
    lines = [_render_line(ln, url).rstrip() for ln in text.split("\n")]
    out = "\n".join(lines).strip("\n")
    out = re.sub(r"\n{3,}", "\n\n", out)  # removed blocks leave no gaps
    return out.replace("<code>—</code>", "—")  # missing values stay quiet


def _apply_conditionals(template: str, values: dict) -> str:
    def _rep(m):
        return m.group(2) if values.get(m.group(1)) else ""

    prev = None
    out = template
    while prev != out:  # tolerate accidental nesting by iterating to fixpoint
        prev = out
        out = _IF_RE.sub(_rep, out)
    return out


def _apply_placeholders(text: str, values: dict) -> str:
    def _rep(m):
        space, key = m.group(1), m.group(2)
        if key not in values:
            return m.group(0)  # unknown {key}: leave visible for preview debugging
        if values[key] is None:
            return space + "—"
        if values[key] == "":
            return ""  # empty: swallow one adjacent space, no gaps
        return space + str(values[key])  # escaped once later, per line

    return re.sub(r"( ?)\{(\w+)\}", _rep, text)


def _render_line(line: str, url: str = "") -> str:
    line = line.rstrip()  # empty placeholders leave no trailing gaps
    quoted = line.startswith("> ")
    if quoted:
        line = line[2:]
    line = html.escape(line, quote=True)
    # [[text]] -> blue link (numbers); tappable, no preview. Falls back to plain if no url or text is —.
    if url:
        def _blue(m):
            inner = m.group(1)
            if inner == "—":
                return "—"
            return f'<a href="{html.escape(url, quote=True)}">{inner}</a>'
        line = _BLUE_RE.sub(_blue, line)
    else:
        line = _BLUE_RE.sub(lambda m: m.group(1), line)
    # markup constructs survive escaping; & in URLs becomes &amp; (valid HTML)
    line = _LINK_RE.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', line)
    line = _CODE_RE.sub(lambda m: f"<code>{m.group(1)}</code>", line)
    line = _BOLD_RE.sub(lambda m: f"<b>{m.group(1)}</b>", line)
    if quoted:
        line = f"<blockquote>{line}</blockquote>"
    return line


def known_placeholders() -> tuple:
    return ("side", "symbol", "datetime", "entry", "sl", "t1", "t2",
            "risk", "reward", "reward1", "reward2", "rr", "rr1", "rr2", "exit", "url")


def validate(template: str) -> list:
    """Return list of unknown {placeholders} (empty = clean)."""
    used = set(re.findall(r"\{(\w+)\}", template))
    ifs = set(re.findall(r"\{#if (\w+)\}", template))
    known = set(known_placeholders())
    return sorted((used | ifs) - known)
