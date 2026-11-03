"""GeM catalogue page (bidplus.gem.gov.in/bidding/bid/showCatalogue/<token>) -> list of spec rows.

Rows are server-rendered in <tbody class="compareContainer"> (category cell spans several rows). Each row:
{"category", "name", "values", "narrowed"}; narrowed = the buyer left a single value (vs the full allowed list).
A few pages fill the table client-side and come back empty: then [].
"""
from bs4 import BeautifulSoup


def parse(html):
    soup = BeautifulSoup(html, "lxml")
    tb = soup.find("tbody", class_="compareContainer")
    out, cat, left = [], None, 0
    for tr in (tb.find_all("tr") if tb else []):
        cells = tr.find_all(["td", "th"])
        if left <= 0 and len(cells) >= 3:
            cat = cells[0].get_text(" ", strip=True)
            left = int(cells[0].get("rowspan") or 1)
            cells = cells[1:]
        if len(cells) < 2:
            left -= 1
            continue
        values = cells[1].get_text(" ", strip=True)
        out.append({"category": cat, "name": cells[0].get_text(" ", strip=True), "values": values,
                    "narrowed": "," not in values})
        left -= 1
    return out
