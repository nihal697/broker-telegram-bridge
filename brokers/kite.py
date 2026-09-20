"""Zerodha Kite adapter (stub) — plug Kite Connect order_update WS into Bridge.

Contribute if you use Kite: map Kite's order fields to canonical dict and
implement run_forever().

Kite Connect docs: https://kite.trade/docs/connect/v3/
Fields to map: tradingsymbol, transaction_type, price, trigger_price,
               status, order_id, quantity

Then call await on_message(raw_update).

See docs/BROKERS.md for canonical shape.
"""
from __future__ import annotations

import logging

log = logging.getLogger("brokers.kite")


def normalize_kite(raw: dict) -> dict:
    return {
        "Symbol": raw.get("tradingsymbol") or raw.get("symbol"),
        "TxnType": raw.get("transaction_type") or raw.get("side"),
        "Price": raw.get("price"),
        "TriggerPrice": raw.get("trigger_price") or raw.get("triggerPrice"),
        "Status": raw.get("status") or raw.get("orderStatus"),
        "OrderNo": raw.get("order_id") or raw.get("orderId"),
        "Quantity": raw.get("quantity") or raw.get("qty"),
    }


async def run_forever(on_message, get_token=None):
    raise NotImplementedError("Kite adapter not yet implemented — see docs/BROKERS.md and PRs welcome")
