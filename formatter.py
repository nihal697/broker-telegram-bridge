"""Telegram call formatting — send immediately, edit when SL/target arrive.

Premium-minimal style: breathing room between sections, one accent (bold)
reserved for live prices, no footer/branding, missing levels render as —.

Contract (used by grouper + sender):
- render_call(position) -> HTML string for Bot.send_message / edit_message_text
- Position holds entry always; sl/t1/t2 optional (None = not placed yet).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Position:
    symbol: str
    side: str  # BUY or SELL (entry direction)
    entry_price: float | None = None
    entry_status: str = "TRADED"
    entry_time: str = ""
    qty: int = 0
    lot_size: int = 0  # e.g. 65 for NIFTY, 0 = unknown
    product: str = ""
    order_id: str = ""
    sl: float | None = None
    t1: float | None = None
    t2: float | None = None
    trail: float | None = None
    exit_info: str = ""  # e.g. "✅ T1 HIT @165" / "🛑 SL HIT @118"
    remarks: str = ""

    _FIELDS = ("symbol", "side", "entry_price", "entry_status", "entry_time",
               "qty", "lot_size", "product", "order_id", "sl", "t1", "t2", "trail",
               "exit_info", "remarks")

    def to_dict(self) -> dict:
        return {f: getattr(self, f) for f in self._FIELDS}

    @classmethod
    def from_dict(cls, d: dict) -> "Position":
        return cls(**{k: d[k] for k in cls._FIELDS if k in d})


# RR multiples for the two computed targets.
T1_RR = 1.5
T2_RR = 2.0


def rr_levels(entry: float | None, sl: float | None, side: str):
    """Return (t1, t2) from entry/SL using fixed RR, direction-aware.

    BUY: targets above entry. SELL: targets below entry. None if inputs missing.
    """
    try:
        if entry is None or sl is None:
            return None, None
        r = abs(entry - sl)
        if r <= 0:
            return None, None
        sign = 1 if side.upper() == "BUY" else -1
        return entry + sign * T1_RR * r, entry + sign * T2_RR * r
    except Exception:
        return None, None


def _n(v: float | None):
    """Format a number or None (engine renders None as —)."""
    if v is None:
        return None
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _pts(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _fmt_time(raw: str) -> str:
    """'2024-09-11 14:39:29' -> '02:39 PM - 11 Sep 2024' (time - date year).

    Pass through if unparseable.
    """
    from datetime import datetime

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d-%m-%Y %H:%M:%S"):
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            return f"{dt.strftime('%I:%M %p')} - {dt.strftime('%d %b %Y')}"
        except (ValueError, AttributeError):
            continue
    return (raw or "").strip()


def render_call(p: Position, template: str | None = None, chart_url: str = "https://web.dhan.co") -> str:
    """Render via the Telegram-editable template (default = user spec)."""
    import template_engine as te

    side = (p.side or "").upper()
    t1, t2 = rr_levels(p.entry_price, p.sl, side)
    r = abs(p.entry_price - p.sl) if p.entry_price is not None and p.sl is not None else None
    if r is not None and r <= 0:
        r, t1, t2 = None, None, None
    r1 = _n(abs(t1 - p.entry_price)) if t1 is not None else None
    r2 = _n(abs(t2 - p.entry_price)) if t2 is not None else None
    values = {
        "side": side,
        "symbol": p.symbol or "UNKNOWN",
        "datetime": _fmt_time(p.entry_time) or "",
        "entry": _n(p.entry_price),
        "sl": _n(p.sl),
        "t1": _n(t1),
        "t2": _n(t2),
        "risk": _n(r),
        "reward": f"{r1} to {r2}" if r1 is not None else None,
        "reward1": r1,
        "reward2": r2,
        "rr": f"1:{T1_RR:g} to 1:{T2_RR:g}" if t1 is not None else None,
        "rr1": f"1:{T1_RR:g}" if t1 is not None else None,
        "rr2": f"1:{T2_RR:g}" if t1 is not None else None,
        "exit": p.exit_info or None,
        "url": chart_url,  # kept for [[ ]] compatibility; unused when template uses `code`
    }
    return te.render(template if template is not None else DEFAULT_TEMPLATE, values)


DEFAULT_TEMPLATE = """🦉PAPER TRADE
**___________________________**

**{side} {symbol}{#if datetime} | {datetime}{#endif}**

**Entry:** `{entry}`
**SL:** `{sl}`
**Target 1:** `{t1}`  (Book Half)
**Target 2:** `{t2}`  (Book Other Half)
**Lot Size:** According to risk appetite
{#if sl}
**___________________________**

**Risk:** `{risk}` points/lot
**Reward:** `{reward1}` to `{reward2}` points/lot
**Risk-Reward:** `{rr1}` to `{rr2}`{#endif}
{#if exit}
{exit}{#endif}
**___________________________**

you are welcome to join our small community :)

[**TRADING THINGS**](https://t.me/tradiingthiings) **X** [**NIFTY33**](https://t.me/niftyy333)

> **DISCLAIMER:** WE ARE NOT SEBI REGISTERED ADVISOR. THIS CALL IS FOR EDUCATION PURPOSES ONLY"""

# Backwards-compatible helper for tests / simple callers
def render_entry_only(symbol: str, side: str, entry: float, qty: int = 0) -> str:
    return render_call(Position(symbol=symbol, side=side, entry_price=entry, qty=qty))
