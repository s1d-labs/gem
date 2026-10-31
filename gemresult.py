"""GeM bid-result page (bidplus.gem.gov.in/bidding/bid/getBidResultView/<id>) -> dict (copy of investigation/gemparse/result.py).

Reads the two well-formed tables (technical evaluation, financial evaluation) cell by cell. The page's buyer
'Address' field (official's e-mail and name) is deliberately not extracted. A non-bid id returns a blank template
(empty 'Bid Number'); that comes back as {"bid_number": None, ...}.
"""
import re

from bs4 import BeautifulSoup

BID_RE = re.compile(r"GEM/(20\d\d)/([BR])/(\d+)")
MONEY_RE = re.compile(r"[\d,]+(?:\.\d+)?")


LABELS = r"(?:Bid Number|Bid Status|Quantity|Ministry|Department|Organisation|Office|Address|Bid Start Date|Bid End Date|Item Category|Buyer)"


def _field(soup, label, text=None):
    text = text if text is not None else soup.get_text(" ", strip=True)
    m = re.search(re.escape(label) + r"\s*:\s*(.*?)\s*(?=" + LABELS + r"\s*:|$)", text)
    v = m.group(1).strip() if m else ""
    return v[:300] or None


def _money(s):
    m = MONEY_RE.search((s or "").replace("`", ""))
    return float(m.group(0).replace(",", "")) if m else None


def _seller(cell):
    # "A S ENTERPRISES | Under PMA" or "P R ENTERPRISES ( MSE Social Category:General ) | Under PMA"
    parts = [p.strip() for p in cell.get_text("|", strip=True).split("|") if p.strip()]
    name = parts[0] if parts else ""
    tags = " ".join(parts[1:])
    name = re.sub(r"\s*\(\s*(MII|MSE[^)]*)\s*\)", "", name).strip()
    return name, tags


def parse(html):
    soup = BeautifulSoup(html, "lxml")
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    bn = _field(soup, "Bid Number", text)
    m = BID_RE.search(bn or "")
    out = {
        "bid_number": m.group(0) if m else None,
        "quantity": None, "ministry": _field(soup, "Ministry", text), "department": _field(soup, "Department", text),
        "organisation": _field(soup, "Organisation", text), "technical": [], "financial": [],
    }
    q = re.match(r"([\d,]+)\b", _field(soup, "Quantity", text) or "")
    if q:
        out["quantity"] = int(q.group(1).replace(",", ""))
    for t in soup.find_all("table"):
        trs = t.find_all("tr")
        if not trs:
            continue
        head = " ".join(c.get_text(" ", strip=True) for c in trs[0].find_all(["th", "td"]))
        rows = [tr.find_all(["td", "th"]) for tr in trs[1:]]
        rows = [r for r in rows if r and r[0].get_text(strip=True).isdigit()]
        if "Participated" in head and "Status" in head:
            for r in rows:
                if len(r) < 6:
                    continue
                name, tags = _seller(r[1])
                offered = r[2].get_text(" ", strip=True)
                mk = re.search(r"Make\s*:\s*(.*?)\s*(?:Model\s*:|$)", offered)
                md = re.search(r"Model\s*:\s*(.*)$", offered)
                out["technical"].append({
                    "s_no": int(r[0].get_text(strip=True)), "seller": name, "seller_tags": tags,
                    "make": mk.group(1).strip() if mk else None, "model": md.group(1).strip() if md else None,
                    "submitted": r[3].get_text(" ", strip=True) or None, "mse_mii": r[4].get_text(" ", strip=True) or None,
                    "status": r[5].get_text(" ", strip=True) or None})
        elif "Rank" in head and "Total Price" in head:
            for r in rows:
                if len(r) < 5:
                    continue
                name, tags = _seller(r[1])
                out["financial"].append({
                    "s_no": int(r[0].get_text(strip=True)), "seller": name, "seller_tags": tags,
                    "item": re.sub(r"^Item Categories\s*:?\s*", "", r[2].get_text(" ", strip=True)) or None,
                    "total_price": _money(r[3].get_text(" ", strip=True)), "rank": r[4].get_text(" ", strip=True) or None})
    out["n_technical"] = len(out["technical"])
    out["n_qualified"] = sum(1 for x in out["technical"] if (x["status"] or "").lower() == "qualified")
    out["n_financial"] = len(out["financial"])
    out["blank_template"] = out["bid_number"] is None and "01-01-1970" in text
    return out
