"""auth_refresh tests — renew-first, TOTP fallback, .env patching (mocked HTTP)."""
import json
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import auth_refresh as ar


class FakeResp:
    def __init__(self, payload, fail=False):
        self.payload = payload
        self.fail = fail

    def raise_for_status(self):
        if self.fail:
            raise RuntimeError("http 401")

    def json(self):
        return self.payload


def _fake_requests(handler):
    mod = types.ModuleType("requests")
    mod.post = handler
    sys.modules["requests"] = mod


def test_save_patches_env():
    tmp = tempfile.mkdtemp()
    ar.BASE_DIR = __import__("pathlib").Path(tmp)
    (ar.BASE_DIR / ".env").write_text("A=1\nDHAN_ACCESS_TOKEN=OLD\nB=2\n")
    ar._save("NEWTOKEN", {"accessToken": "NEWTOKEN"})
    text = (ar.BASE_DIR / ".env").read_text()
    assert "DHAN_ACCESS_TOKEN=NEWTOKEN" in text and "OLD" not in text
    assert (ar.BASE_DIR / "data" / "token.json").exists()


def test_renew_first():
    tmp = tempfile.mkdtemp()
    ar.BASE_DIR = __import__("pathlib").Path(tmp)
    (ar.BASE_DIR / ".env").write_text("DHAN_ACCESS_TOKEN=OLD\n")
    calls = []

    def post(url, headers=None, params=None, timeout=None):
        calls.append(url)
        assert "RenewToken" in url
        assert headers["access-token"] == "OLD"
        return FakeResp({"accessToken": "RENEWED", "expiryTime": "tomorrow"})

    import requests as _rq
    _rq.get, _rq.post = post, post
    _fake_requests_module = types.ModuleType("requests")
    _fake_requests_module.get = post
    _fake_requests_module.post = post
    sys.modules["requests"] = _fake_requests_module
    out = ar.renew_token("CID", "OLD")
    assert out == "RENEWED" and len(calls) == 1


def test_refresh_totp_primary():
    tmp = tempfile.mkdtemp()
    ar.BASE_DIR = __import__("pathlib").Path(tmp)
    (ar.BASE_DIR / ".env").write_text("DHAN_ACCESS_TOKEN=OLD\n")
    os.environ["DHAN_CLIENT_ID"] = "CID"
    os.environ["DHAN_ACCESS_TOKEN"] = "OLD"
    os.environ["DHAN_PIN"] = "123456"
    os.environ["DHAN_TOTP_SECRET"] = "JBSWY3DPEHPK3PXP"
    calls = []

    def post(url, headers=None, params=None, timeout=None):
        calls.append(url)
        assert "generateAccessToken" in url, url  # renew must NOT be attempted
        return FakeResp({"accessToken": "FRESH", "expiryTime": "tomorrow"})

    both = types.ModuleType("requests")
    both.get = post
    both.post = post
    sys.modules["requests"] = both
    fake_pyotp = types.ModuleType("pyotp")

    class FakeTOTP:
        def __init__(self, s):
            assert s == "JBSWY3DPEHPK3PXP"

        def now(self):
            return "123456"

    fake_pyotp.TOTP = FakeTOTP
    sys.modules["pyotp"] = fake_pyotp
    try:
        out = ar.refresh()
    finally:
        for k in ("DHAN_CLIENT_ID", "DHAN_ACCESS_TOKEN", "DHAN_PIN", "DHAN_TOTP_SECRET"):
            os.environ.pop(k, None)
        sys.modules.pop("requests", None)
        sys.modules.pop("pyotp", None)
    assert out == "FRESH" and len(calls) == 1


def test_refresh_falls_back_to_renew():
    tmp = tempfile.mkdtemp()
    ar.BASE_DIR = __import__("pathlib").Path(tmp)
    (ar.BASE_DIR / ".env").write_text("DHAN_ACCESS_TOKEN=OLD\n")
    os.environ["DHAN_CLIENT_ID"] = "CID"
    os.environ["DHAN_ACCESS_TOKEN"] = "OLD"
    # no PIN/TOTP -> generate skipped, renew used
    calls = []

    def post(url, headers=None, params=None, timeout=None):
        calls.append(url)
        assert "RenewToken" in url, url
        return FakeResp({"token": "RENEWED", "expiryTime": "tomorrow"})

    both = types.ModuleType("requests")
    both.get = post
    both.post = post
    sys.modules["requests"] = both
    try:
        out = ar.refresh()
    finally:
        for k in ("DHAN_CLIENT_ID", "DHAN_ACCESS_TOKEN"):
            os.environ.pop(k, None)
        sys.modules.pop("requests", None)
    assert out == "RENEWED" and len(calls) == 1
