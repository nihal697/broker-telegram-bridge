"""Generic webhook adapter — POST any order JSON to Bridge.handle_event().

No broker SDK needed. Run this with a tiny FastAPI/Flask endpoint that calls
await bridge.handle_event(payload).

Example POST body:
  {
    "symbol": "NIFTY 24500 CE",
    "side": "BUY",
    "price": 142.5,
    "trigger": 118,
    "status": "TRADED",
    "order_no": "E1",
    "qty": 50
  }

Or Dhan-like raw: {"Symbol": "...", "TxnType": "B", "TradedPrice": 142.5, "Status": "TRADED", ...}
Both shapes are normalized by grouper.normalize().
"""
from __future__ import annotations

import logging

log = logging.getLogger("brokers.generic")


async def run_forever(on_message, get_token=None):
    """Placeholder — for generic broker you call on_message directly from your webhook."""
    log.info("Generic adapter has no WS loop — POST orders to Bridge.handle_event() directly")
    # Keep alive forever so main.py doesn't exit; real orders arrive via HTTP handler you add.
    import asyncio

    while True:
        await asyncio.sleep(3600)
