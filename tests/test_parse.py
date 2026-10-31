"""Parsing tests on saved GeM result pages (buyer official's name, address, e-mail and phone removed from the saved copies)."""
from pathlib import Path

from gemresult import parse

PAGES = Path(__file__).parent / "pages"


def page(name):
    return (PAGES / name).read_text(encoding="utf-8", errors="ignore")


def test_open_bid_2018():
    r = parse(page("result_286703.html"))
    assert r["bid_number"] == "GEM/2018/B/40693" and r["quantity"] == 48
    assert r["n_technical"] == 21 and r["n_qualified"] == 1
    q = [x for x in r["technical"] if x["status"] == "Qualified"][0]
    assert q["seller"] == "SHREEG ELECTRICALS" and q["make"] == "shreeg"
    assert r["financial"][0]["total_price"] == 110256.0 and r["financial"][0]["rank"] == "L1"


def test_three_quotes_2025():
    r = parse(page("result_7450761.html"))
    assert r["bid_number"] == "GEM/2025/B/5886278"
    assert [x["total_price"] for x in r["financial"]] == [298435.0, 298450.0, 299636.0]
    assert {x["model"] for x in r["technical"] if x["status"] == "Qualified"} == {"ET1818+"}


def test_no_personal_fields():
    r = parse(page("result_7450761.html"))
    assert not any(k in r for k in ("name", "address", "email", "phone"))


def test_blank_template():
    r = parse("<html><body>Bid Number: Bid Status: Active Quantity: Bid Start Date / Time: 01-01-1970 05:30:00</body></html>")
    assert r["bid_number"] is None and r["blank_template"] and r["n_technical"] == 0
