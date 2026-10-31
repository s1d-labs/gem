# gem: GeM bid-result pages and bid documents

A family of the s1d-labs scrape pool. It fetches public pages of GeM's bid portal (bidplus.gem.gov.in) by GeM's internal bid id:

| Task | Page | Stored |
|---|---|---|
| `results` | `/bidding/bid/getBidResultView/<id>`: every bidder, offered make/model, technical result, price-stage quotes | one record per id (parsed, `gemresult.py`) + the page gzipped at `<project>/results/<id>.html.gz` in the family's bucket |
| `pdfs` | `/showbidDocument/<id>`: the bid document | `<project>/pdf/<id>.pdf` in the family's bucket + one record per id (size, checksum) |

- GeM answers only from India: the projects use `geo="IN"`, so the work runs on the pool's India servers only.
- Pace: about 2.5 requests/s per worker outside 10:00-18:00 IST and about 0.5 requests/s inside it (GeM itself returns about 10%
  HTTP 500 at midday), at most 8 workers on the host; the hub's back-off applies on top (`gemcommon.py`).
- Personal data: result pages carry the buyer official's name, address, e-mail and phone. The parser never extracts them; raw pages
  stay in the private bucket; the saved test pages here have them removed.
- Pilot: Chhattisgarh state buyers' bids (`data/cg_pids.txt.gz`, 20,116 ids). National lists get added after the pilot is checked.

Setup: change `family.py`, then Actions -> setup. Tests: `python -m pytest tests`.
