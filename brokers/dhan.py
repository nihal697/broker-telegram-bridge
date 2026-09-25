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
            if get_token:
                try:
                    fresh = get_token()
                    if fresh:
                        token = fresh
                except Exception as e:
                    log.error("pre-connect token refresh failed: %s", e)

            async for ws in connect(url, ping_interval=20, ping_timeout=20):
                async def _watch_token(ws_conn, cur_tok):
                    while True:
                        await asyncio.sleep(30)
                        if get_token:
                            try:
                                fresh = get_token()
                                if fresh and fresh != cur_tok:
                                    log.info("Access token rotated — closing WS to re-auth with new token")
                                    await ws_conn.close()
                                    break
                            except Exception as ex:
                                log.error("token watcher error: %s", ex)

                watcher = asyncio.create_task(_watch_token(ws, token))
                try:
                    auth = {"LoginReq": {"MsgCode": 42, "ClientId": client_id, "Token": token},
                            "UserType": "SELF"}
                    await ws.send(json.dumps(auth))
                    log.info("WS connected + auth sent (ClientId: %s)", client_id)
                    backoff = 5
                    async for raw in ws:
                        if isinstance(raw, bytes):
                            log.warning("WS received binary packet (len=%d): %r", len(raw), raw)
                            if raw.startswith(b"2") or (len(raw) > 0 and raw[0] == 50):
                                log.error("Dhan WS returned Error Packet (MsgCode 50): %r — reconnecting", raw)
                                await ws.close()
                            continue
                        log.info("WS received msg: %s", raw)
                        try:
                            data = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        # server may wrap: {"OrderUpdate": {...}} / {"Data": {...}} / raw order dict
                        # Dhan migrated Sep 2026 from OrderUpdate to Data + lowerCamelCase
                        update = data.get("OrderUpdate") or data.get("Data") or data
                        # if Data was the envelope, keep inner dict as update (normalize also unwraps as safety)
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
                finally:
                    watcher.cancel()
        except Exception as e:
            log.error("WS error: %s — retry in %ss", e, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 120)
