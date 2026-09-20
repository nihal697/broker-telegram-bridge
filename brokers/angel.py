"""Angel One adapter (stub) — plug SmartAPI order WS into Bridge.

Contribute if you use Angel: map Angel's order update fields to canonical dict
and implement run_forever() similar to brokers/dhan.py.

Angel SmartAPI docs: https://smartapi.angelone.in/
Fields to map: tradingsymbol, transactiontype (BUY/SELL), price, triggerprice,
               status, orderid, quantity

Then call await on_message(raw_update) for each order.

This stub keeps the repo broker-agnostic while keeping Dhan as the reference.
See docs/BROKERS.md for canonical shape.
"""
from __future__ import annotations

import logging

log = logging.getLogger("brokers.angel")


def normalize_angel(raw: dict) -> dict:
    """Example mapper — adjust field names to your Angel feed."""
    return {
        "Symbol": raw.get("tradingsymbol") or raw.get("symbol"),
        "TxnType": raw.get("transactiontype") or raw.get("side"),
        "Price": raw.get("price"),
        "TriggerPrice": raw.get("triggerprice") or raw.get("triggerPrice"),
        "Status": raw.get("status") or raw.get("orderStatus"),
        "OrderNo": raw.get("orderid") or raw.get("orderId"),
        "Quantity": raw.get("quantity") or raw.get("qty"),
    }


async def run_forever(on_message, get_token=None):
    raise NotImplementedError("Angel adapter not yet implemented — see docs/BROKERS.md and PRs welcome")
