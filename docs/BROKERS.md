# Brokers — how to add support for any broker

Core (`main.py` → `grouper.py` → `formatter.py` → `telegram_sender.py`) is broker-agnostic.
Only the adapter that feeds `main.Bridge.handle_event(update)` is broker-specific. Any broker that can give you order updates (WS or webhook) works.

## Canonical order dict

`grouper.normalize()` accepts both Dhan WS and REST shapes and returns:

```python
{
  "side": "BUY" | "SELL",
  "status": "TRADED" | "PENDING" | "PART_TRADED" | "CANCELLED" | ...,
  "symbol": "NIFTY 24500 CE",
  "order_no": "OrderNo / orderId",
  "algo": "AlgoOrdNo",        # Super Order / BO linking, optional
  "leg": "STOP_LOSS_LEG",     # or "TARGET_LEG", optional
  "otype": "STOP_LOSS_MARKET",# OrderType, optional
  "price": 142.5,             # TradedPrice / Price
  "trigger": 118,             # TriggerPrice for SL
  "qty": 50,
  "product": "I",
  "remarks": "SL:118",
  "ts": "2024-09-11 10:16:02",
  "target_price": None,       # super-order target
  "sl_price": None,           # super-order SL
  "now": 1234567890.0,
}
```

Minimum viable: `symbol`, `side`, `status`, `price` or `trigger`, `order_no`.

Target display is **RR-computed** (`entry ± 1.5R / 2R`), so you never need to map your broker’s limit price.

## Adding a broker

1. Create `brokers/<broker>.py`:

```python
from __future__ import annotations
import asyncio, json, logging

def normalize(update: dict) -> dict:
    # Map broker raw → canonical (see grouper.normalize for reference)
    pass

async def run_forever(on_message, get_token=None):
    # connect to broker WS, auth, for each order update: await on_message(update)
    # use websockets or broker SDK; handle reconnect with backoff
    pass
```

2. Wire it in `config.py` (`BROKER` env) and `main.py:_amain()`:

```python
if broker == "dhan":
    from dhan_ws import run_forever
elif broker == "angel":
    from brokers.angel import run_forever
elif broker == "kite":
    from brokers.kite import run_forever
```

3. Add adapter-specific env (e.g. `ANGEL_API_KEY`, `ANGEL_CLIENT_ID`) to `.env.example`.

## Examples

### Angel One SmartAPI (sketch)

```python
# brokers/angel.py
def normalize(u): # Angel feed shape
    return {"symbol": u["tradingsymbol"], "side": "BUY" if u["transactiontype"]=="BUY" else "SELL",
            "status": u["status"], "price": float(u["price"] or 0) or None,
            "trigger": float(u["triggerprice"] or 0) or None, "order_no": u["orderid"], ...}
```

### Generic webhook (no SDK)

Run a tiny FastAPI / Flask endpoint that calls `bridge.handle_event(json_from_webhook)` directly — works for any broker that can POST order JSON.

## Testing a new adapter

- Keep `DRY_RUN=true`, feed synthetic updates to `PositionTracker` (see `test_grouper.py`).
- Use `local_send_test.py` or `replay_test.py` to prove `SEND` → `EDIT` same `mid` in your Telegram channel.

PRs for new brokers are welcome — keep adapters small, no core changes.
