"""Template engine tests — markup, escaping, conditionals, validation."""
from template_engine import render, validate


def test_bold_code_link():
    out = render("**Entry:** `142.5` [X](https://t.me/abc)", {})
    assert out == "<b>Entry:</b> <code>142.5</code> " \
        '<a href="https://t.me/abc">X</a>'


def test_quote_line():
    out = render("> **DISCLAIMER:** hello", {})
    assert out == "<blockquote><b>DISCLAIMER:</b> hello</blockquote>"


def test_unknown_placeholder_stays_visible():
    out = render("S: {sl} {nope}", {"sl": "118"})
    assert out == "S: 118 {nope}"


def test_missing_value_dash():
    out = render("SL: `{sl}`", {"sl": None})
    assert out == "SL: —"


def test_conditionals():
    tpl = "A{#if sl}\nSL: {sl}{#endif}\nB"
    assert render(tpl, {"sl": "118"}) == "A\nSL: 118\nB"
    assert render(tpl, {"sl": None}) == "A\nB"


def test_removed_blocks_leave_no_gaps():
    tpl = "A\n{#if sl}\nSL: {sl}\n{#endif}\n\nB"
    assert render(tpl, {"sl": None}) == "A\n\nB"


def test_trailing_space_stripped():
    assert render("**{side} {symbol} {datetime}**",
                  {"side": "BUY", "symbol": "X", "datetime": ""}) == "<b>BUY X</b>"


def test_xss_escaped_once():
    out = render("S: {symbol}", {"symbol": "<b>evil</b>"})
    assert out == "S: &lt;b&gt;evil&lt;/b&gt;"
    assert "&amp;lt;" not in out


def test_validate():
    assert validate("**{side}** {bogus} {#if alsobad}x{#endif}") == ["alsobad", "bogus"]
    assert validate("{side} {sl}") == []
