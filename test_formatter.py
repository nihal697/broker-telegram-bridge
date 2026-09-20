"""Slice 1 tests — exact user-approved template (bold labels, mono numbers)."""
from formatter import Position, render_call, rr_levels, _fmt_time, DEFAULT_TEMPLATE
from template_engine import validate


def test_rr_levels_buy():
    t1, t2 = rr_levels(142.5, 118, "BUY")
    assert abs(t1 - 179.25) < 1e-9 and abs(t2 - 191.5) < 1e-9


def test_rr_levels_sell_flips():
    t1, t2 = rr_levels(200, 220, "SELL")
    assert abs(t1 - 170) < 1e-9 and abs(t2 - 160) < 1e-9


def test_rr_levels_missing():
    assert rr_levels(None, 118, "BUY") == (None, None)
    assert rr_levels(100, 100, "BUY") == (None, None)


def test_fmt_time_is_time_dash_date_year():
    assert _fmt_time("2024-09-11 14:39:29") == "02:39 PM - 11 Sep 2024"
    assert _fmt_time("garbage") == "garbage"


def test_default_template_is_clean():
    assert validate(DEFAULT_TEMPLATE) == []


def test_entry_only_placeholders_and_disclaimer():
    msg = render_call(Position(symbol="NIFTY 24500 CE", side="BUY",
                               entry_price=142.5, qty=50))
    assert "<b>Target 1:</b> —  (Book Half)" in msg and "<b>Target 2:</b> —  (Book Other Half)" in msg
    assert "Risk:" not in msg  # hidden until SL known
    assert "DISCLAIMER:" in msg and "<blockquote>" in msg
    assert "🦉PAPER TRADE" in msg


def test_full_call_matches_user_spec():
    msg = render_call(Position(symbol="NIFTY 24500 CE", side="BUY",
                               entry_price=142.5, qty=50,
                               entry_time="2024-09-11 14:39:29", sl=118))
    assert "🦉PAPER TRADE" in msg
    assert "<b>BUY NIFTY 24500 CE | 02:39 PM - 11 Sep 2024</b>" in msg
    assert "<b>Entry:</b> <code>142.5</code>" in msg
    assert "<b>SL:</b> <code>118</code>" in msg
    assert "<b>Target 1:</b> <code>179.25</code>  (Book Half)" in msg
    assert "<b>Target 2:</b> <code>191.5</code>  (Book Other Half)" in msg
    assert "<b>Lot Size:</b> According to risk appetite" in msg
    assert "<b>Risk:</b> <code>24.5</code> points/lot" in msg
    assert "<b>Reward:</b> <code>36.75</code> to <code>49</code> points/lot" in msg
    assert "<b>Risk-Reward:</b> <code>1:1.5</code> to <code>1:2</code>" in msg
    assert '<a href="https://t.me/tradiingthiings"><b>TRADING THINGS</b></a> ' \
        '<b>X</b> <a href="https://t.me/niftyy333"><b>NIFTY33</b></a>' in msg


def test_sell_side():
    msg = render_call(Position(symbol="Y", side="SELL", entry_price=200,
                               qty=1, sl=220))
    assert "<b>SELL Y</b>" in msg
    assert "<b>Target 1:</b> <code>170</code>" in msg


def test_custom_chart_url():
    # chart_url param is kept for [[ ]] backwards compat; mono `code` ignores it
    msg = render_call(Position(symbol="X", side="BUY", entry_price=10, sl=9),
                      chart_url="https://example.com")
    assert "<code>10</code>" in msg


def test_blue_fallback_without_url():
    from template_engine import render
    assert render("[[42]]", {"url": ""}) == "42"


def test_html_escaped():
    msg = render_call(Position(symbol="<b>evil</b>", side="BUY",
                               entry_price=10, qty=1))
    assert "&lt;b&gt;evil" in msg


def test_exit_block_separated():
    msg = render_call(Position(symbol="Y", side="BUY", entry_price=10, qty=1,
                               sl=9, exit_info="🔻SL hit @ 9"))
    assert "\n\n🔻SL hit @ 9\n" in msg


def test_custom_template_override():
    msg = render_call(Position(symbol="X", side="BUY", entry_price=10,
                               sl=9), template="**{side}** `{entry}`")
    assert msg == "<b>BUY</b> <code>10</code>"

    # plain numbers when template has no markup around placeholder
    msg2 = render_call(Position(symbol="X", side="BUY", entry_price=10,
                                sl=9), template="**{side}** {entry}")
    assert msg2 == "<b>BUY</b> 10"
