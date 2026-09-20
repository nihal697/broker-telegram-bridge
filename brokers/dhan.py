"""Dhan Live Order Update WS client — catches ALL orders incl. manual app trades.

Endpoint: wss://api-order-update.dhan.co
Auth: {"LoginReq":{"MsgCode":42,"ClientId":"...","Token":"..."},"UserType":"SELF"}
Reconnect: infinite `async for ws in connect(...)` + backoff (Context7 pattern).
"""
from __future__ import annotations

import asyncio
import json
import logging

log = logging.getLogger("dhan_ws")


async def run_forever(url: str, client_id: str, token: str, on_message, get_token=None):
    """Connect, auth, dispatch each JSON update to on_message(update: dict). Never returns."""
    from websockets.asyncio.client import connect
    from websockets.exceptions import ConnectionClosed

    backoff = 5
    while True:
        try:
            async for ws in connect(url, ping_interval=20, ping_timeout=20):
                try:
                    auth = {"LoginReq": {"MsgCode": 42, "ClientId": client_id, "Token": token},
                            "UserType": "SELF"}
                    await ws.send(json.dumps(auth))
                    log.info("WS connected + auth sent")
                    backoff = 5
                    async for raw in ws:
                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        # server may wrap: {"OrderUpdate": {...}} or raw order dict
                        update = data.get("OrderUpdate", data)
                        if isinstance(update, list):
                            for u in update:
                                await on_message(u)
                        else:
                            await on_message(update)
                except ConnectionClosed:
                    log.warning("WS closed, reconnecting...")
                    if get_token:
                        try:
                            token = get_token() or token
                        except Exception as e:
                            log.error("token refresh failed: %s", e)
                    continue
        except Exception as e:
            log.error("WS error: %s — retry in %ss", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 120)
