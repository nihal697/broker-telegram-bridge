"""Daily Dhan token refresh — Dhan access tokens live only 24h.

Strategy (in order):
  1. TOTP generate — mints a brand-new token from scratch. Works even from an
     expired/dead token and is immune to renew quirks (GET-not-POST, `token`
     vs `accessToken` field, single-rotation-per-token). Needs DHAN_PIN +
     DHAN_TOTP_SECRET. Primary path now that the secret is stored.
  2. RenewToken (GET) — extends the current *web-generated* token by 24h.
     Fallback for when TOTP creds are missing.

Run via systemd timer at 07:55 IST (before market open). Writes fresh token to
data/token.json AND updates DHAN_ACCESS_TOKEN in .env. main.py re-reads .env
via current_token() and reconnects WS with the new token.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
AUTH_BASE = "https://auth.dhan.co"
API_BASE = "https://api.dhan.co/v2"


def _save(token: str, meta: dict) -> str:
    (BASE_DIR / "data").mkdir(exist_ok=True)
    (BASE_DIR / "data" / "token.json").write_text(json.dumps(meta, indent=2))
    env = BASE_DIR / ".env"
    lines, found = [], False
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("DHAN_ACCESS_TOKEN="):
                lines.append(f"DHAN_ACCESS_TOKEN={token}")
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f"DHAN_ACCESS_TOKEN={token}")
    env.write_text("\n".join(lines) + "\n")
    return token


def renew_token(client_id: str, access_token: str) -> str:
    """Extend a live web token by 24h. Raises on failure.

    NOTE: Dhan's own DhanHQ-py client calls this endpoint with GET
    (not POST) — POST returns DH-905 Input_Exception.
    """
    import requests

    r = requests.get(
        f"{API_BASE}/RenewToken",
        headers={"access-token": access_token, "dhanClientId": client_id},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    # renew endpoint returns {"token": ...}; generate returns {"accessToken": ...}
    token = data.get("accessToken") or data.get("token") or ""
    if not token:
        raise RuntimeError(f"renew gave no accessToken: {data}")
    print(f"renewed, expiry={data.get('expiryTime', '?')}")
    return _save(token, data)


def generate_token(client_id: str, pin: str, totp_secret: str) -> str:
    """Mint a fresh token via TOTP. Raises on failure."""
    import pyotp  # lazy: only needed on server
    import requests

    totp = pyotp.TOTP(totp_secret).now()
    r = requests.post(
        f"{AUTH_BASE}/app/generateAccessToken",
        params={"dhanClientId": client_id, "pin": pin, "totp": totp},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    token = data.get("accessToken", "")
    if not token:
        raise RuntimeError(f"generate gave no accessToken: {data}")
    print(f"generated, expiry={data.get('expiryTime', '?')}")
    return _save(token, data)


def refresh() -> str:
    from config import load_settings

    s = load_settings()
    if not s.dhan_client_id:
        raise SystemExit("DHAN_CLIENT_ID missing in .env")
    # 1) primary: fresh token via TOTP (works from any state)
    if s.dhan_pin and s.dhan_totp_secret:
        try:
            return generate_token(s.dhan_client_id, s.dhan_pin, s.dhan_totp_secret)
        except Exception as e:
            print(f"TOTP generate failed ({e}), trying renew...")
    # 2) fallback: renew the live token (needs it to still be active)
    if s.dhan_access_token:
        return renew_token(s.dhan_client_id, s.dhan_access_token)
    raise SystemExit(
        "TOTP generate failed and no live DHAN_ACCESS_TOKEN to renew — "
        "paste a fresh web token into .env")


if __name__ == "__main__":
    sys.exit(0 if refresh() else 1)
