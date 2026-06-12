"""Dashboard v2 "Terminal Pro" shell tests (Task 1)."""
import re
import sys

sys.path.insert(0, "/Users/jonaspenaso/Desktop/Phmex-S")


def test_shell_structure():
    import web_dashboard as wd
    html = wd.build_html()
    # chart node must live OUTSIDE the swapped #content div
    content_pos = html.index('id="content"')
    equity_pos = html.index('id="equity-root"')
    assert equity_pos > html.index("<body")
    content_div = re.search(r'<div id="content".*?</div>\s*<!-- /content -->', html, re.S)
    assert content_div is not None
    assert 'id="equity-root"' not in content_div.group(0)
    # terminal palette present, old palette gone
    assert "#000204" in html and "#f0a500" in html
    assert "fonts.googleapis.com" not in html


def test_ticker_present():
    import web_dashboard as wd
    c = wd.build_content()
    assert 'class="ticker"' in c or 'id="ticker"' in wd.build_html()
