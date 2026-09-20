"""Position tracker — one open position per symbol+direction.

Rules (approved):
- Entry TRADED -> ("send", position) immediately, SL/target may be None.
- Later SL/target/exit orders for same symbol -> ("edit", position).
- Super Order / BO legs link via AlgoOrdNo when present.
- Normal orders link via symbol + opposite-side window (default 120s, but an
  open position stays editable until exit/day-end, so late SL still edits).
- Remarks like "SL:118" parsed as fallback (targets always RR-computed).

Accepts BOTH payload shapes:
- WS Live Order Update: Symbol, TxnType B/S, Price/TradedPrice/AvgTradedPrice,
  TriggerPrice, Status, OrderNo, AlgoOrdNo, Product, OrderDateTime...
- REST/Postback: tradingSymbol, transactionType BUY/SELL, price, triggerPrice,
  orderStatus, orderId, legName, targetPrice/stopLossPrice, Remarks.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

from formatter import Position

def _parse_remarks(remarks: str) -> dict:
    """SL fallback only — targets are always RR-computed at render time."""
    out: dict = {}
    m = re.search(r"sl\s*[:=]\s*(\d+(?:\.\d+)?)", remarks or "", re.IGNORECASE)
    if m:
        out["sl"] = float(m.group(1))
    return out


def _lvl_str(lvl) -> str:
    try:
        return f"{float(lvl):g}"
    except (TypeError, ValueError):
        return str(lvl)


def _num(v, default=None):
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def normalize(update: dict) -> dict:
    """Return canonical dict regardless of WS vs REST shape."""
    g = lambda *keys: next((update.get(k) for k in keys if update.get(k) not in (None, "")), None)
    raw_side = g("TxnType", "transactionType", "side") or ""
    side = "BUY" if str(raw_side).upper().startswith("B") else "SELL" if str(raw_side).upper().startswith("S") else str(raw_side).upper()
    raw_status = g("Status", "orderStatus", "status") or ""
    status = str(raw_status).upper()
    symbol = g("Symbol", "tradingSymbol", "symbol") or "UNKNOWN"
    order_no = str(g("OrderNo", "orderId", "order_id") or "")
    algo = str(g("AlgoOrdNo", "algoOrdNo", "algoId") or "")
    leg = str(g("legName", "LegName", "leg") or "").upper()
    otype = str(g("OrderType", "orderType", "order_type") or "").upper()
    price = _num(g("TradedPrice", "AvgTradedPrice", "Price", "price", "tradedPrice", "avgTradedPrice"))
    if not price:
        price = _num(g("targetPrice", "stopLossPrice"))
    trigger = _num(g("TriggerPrice", "triggerPrice", "trigger_price"))
    qty = int(_num(g("Quantity", "quantity", "qty"), 0) or 0)
    product = str(g("Product", "productType", "ProductName", "product") or "")
    remarks = str(g("Remarks", "remarks", "tag", "correlationId", "CorrelationId") or "")
    ts = g("LastUpdatedTime", "OrderDateTime", "updateTime", "createTime", "timestamp")
    return {
        "side": side, "status": status, "symbol": str(symbol), "order_no": order_no,
        "algo": algo, "leg": leg, "otype": otype, "price": price, "trigger": trigger,
        "qty": qty, "product": product, "remarks": remarks, "ts": str(ts or ""),
        "target_price": _num(update.get("targetPrice")), "sl_price": _num(update.get("stopLossPrice")),
        "now": time.time(),
    }


@dataclass
class _OpenSlot:
    position: Position
    entry_side: str
    opened_at: float
    algo: str = ""
    closed: bool = False
    exited_qty: float = 0


class PositionTracker:
    """Single-process tracker. Persist telegram msg mapping in store (Slice 4)."""

    def __init__(self, window_sec: int = 120):
        self.window_sec = window_sec
        self._by_algo: dict[str, _OpenSlot] = {}
        self._by_sym: dict[str, _OpenSlot] = {}  # key: SYMBOL|ENTRY_SIDE

    @staticmethod
    def _sym_key(symbol: str, entry_side: str) -> str:
        return f"{symbol}|{entry_side}"

    def _is_sl(self, ev: dict) -> bool:
        if ev["leg"] == "STOP_LOSS_LEG":
            return True
        if "STOP_LOSS" in ev["otype"]:
            return True
        if ev["sl_price"]:
            return True
        return False

    def _is_target(self, ev: dict) -> bool:
        if ev["leg"] == "TARGET_LEG":
            return True
        if ev["target_price"]:
            return True
        return False

    def handle(self, update: dict) -> tuple[str, Position] | None:
        """Return ("send"|"edit", position) or None (ignore)."""
        ev = normalize(update)
        if ev["status"] in ("REJECTED", "EXPIRED"):
            # rejections on entry with no position -> ignore; on open slot -> edit exit_info
            slot = self._find_slot(ev)
            if slot and not slot.closed:
                slot.position.exit_info = f"⚠️ {ev['status']} {ev['order_no']}"
                return ("edit", slot.position)
            return None

        slot = self._find_slot(ev)
        if slot is None or slot.closed:
            return self._open_new(ev)
        return self._update_slot(slot, ev)

    def restore(self, key: str, pos: Position, algo: str = "") -> None:
        """Reload a persisted open slot (e.g. after process restart)."""
        import time as _t

        slot = _OpenSlot(position=pos, entry_side=pos.side, opened_at=_t.time(), algo=algo)
        self._by_sym[self._sym_key(pos.symbol, pos.side)] = slot
        if algo:
            self._by_algo[algo] = slot

    def _find_slot(self, ev: dict) -> _OpenSlot | None:
        if ev["algo"] and ev["algo"] in self._by_algo:
            return self._by_algo[ev["algo"]]
        # opposite side of an open slot = its exit leg
        for side in ("BUY", "SELL"):
            key = self._sym_key(ev["symbol"], side)
            slot = self._by_sym.get(key)
            if slot and not slot.closed:
                if ev["side"] != slot.entry_side or self._is_sl(ev) or self._is_target(ev):
                    # same symbol, either opposite side or explicit SL/target leg
                    if abs(ev["now"] - slot.opened_at) <= max(self.window_sec, 4 * 3600):
                        return slot
                    # very old slot (>4h): treat as stale, fall through to new
        # same-side scale-in to open slot -> reuse for edit (no spam)
        key = self._sym_key(ev["symbol"], ev["side"])
        slot = self._by_sym.get(key)
        if slot and not slot.closed:
            return slot
        return None

    def _open_new(self, ev: dict) -> tuple[str, Position] | None:
        # Only real order attempts open a call. CANCELLED/REJECTED/EXPIRED with
        # no open slot mean nothing ever traded -> stay silent (no Telegram spam).
        if ev["status"] not in ("TRADED", "PENDING", "TRANSIT", "PART_TRADED"):
            return None
        # Lone SL/target leg with no open slot (e.g. very late >4h stale) must not create a spurious opposite-side call
        # But a super-order entry (side B/S with sl_price/targetPrice attached) IS an entry — don't block it.
        is_pure_sl_leg = (ev["leg"] == "STOP_LOSS_LEG" or "STOP_LOSS" in ev["otype"])
        is_pure_target_leg = (ev["leg"] == "TARGET_LEG")
        # sl_price/targetPrice alone = super-order metadata, not a leg — allow entry
        if is_pure_sl_leg or is_pure_target_leg:
            return None
        # Also block lone trigger-price SL pending with no entry (SELL STOP with trigger but no price)
        if ev["trigger"] and "STOP_LOSS" in ev["otype"] and not ev["price"]:
            # this shape is always an SL leg, never an entry
            return None
        # Only open on entry-side events, not on lone exits
        pos = Position(
            symbol=ev["symbol"], side=ev["side"] or "BUY",
            entry_price=ev["price"], entry_status=ev["status"] or "TRADED",
            entry_time=ev["ts"], qty=ev["qty"], product=ev["product"],
            order_id=ev["order_no"], remarks=ev["remarks"],
        )
        # Super-order placement already carries the stop level.
        if ev["sl_price"]:
            pos.sl = ev["sl_price"]
        if ev["trigger"] and self._is_sl(ev) and pos.sl is None:
            pos.sl = ev["trigger"]
        parsed = _parse_remarks(ev["remarks"])
        pos.sl = pos.sl if pos.sl is not None else parsed.get("sl")
        slot = _OpenSlot(position=pos, entry_side=pos.side, opened_at=ev["now"], algo=ev["algo"])
        self._by_sym[self._sym_key(pos.symbol, pos.side)] = slot
        if ev["algo"]:
            self._by_algo[ev["algo"]] = slot
        return ("send", pos)

    def _update_slot(self, slot: _OpenSlot, ev: dict) -> tuple[str, Position] | None:
        p = slot.position
        changed = False
        if self._is_sl(ev):
            lvl = ev["trigger"] or ev["price"] or ev["sl_price"]
            if lvl and p.sl != lvl:
                p.sl = lvl
                changed = True
            if ev["status"] == "TRADED":
                p.exit_info = f"🔻SL hit @ {_lvl_str(lvl)}"
                slot.closed = True
                return ("edit", p)
        elif self._is_target(ev) or ev["side"] != slot.entry_side:
            # Opposite-side leg = exit (limit target or market square-off).
            # Target-hit labels are OFF by design (done manually) — exits only
            # advance the close counter. Never fall through to averaging below.
            if ev["status"] == "TRADED":
                slot.exited_qty += ev["qty"] or 0
                if p.qty and slot.exited_qty >= p.qty:
                    slot.closed = True
                elif not p.qty:
                    slot.closed = True  # qty unknown: first exit closes
                return ("edit", p)
        else:
            # same-side scale-in / modification: refresh avg/qty
            if ev["price"] and ev["status"] == "TRADED":
                if p.entry_price and ev["qty"]:
                    total = p.qty + ev["qty"]
                    if total > 0:
                        p.entry_price = round((p.entry_price * p.qty + ev["price"] * ev["qty"]) / total, 2)
                    p.qty = total
                elif ev["price"]:
                    p.entry_price = ev["price"]
                    p.qty = p.qty or ev["qty"]
                changed = True
        parsed = _parse_remarks(ev["remarks"])
        if p.sl is None and parsed.get("sl") is not None:
            p.sl = parsed["sl"]
            changed = True
        if ev["status"] == "CANCELLED" and ev["side"] != slot.entry_side:
            p.exit_info = f"ℹ️ exit leg cancelled ({ev['order_no']})"
            changed = True
        if changed:
            return ("edit", p)
        return None
