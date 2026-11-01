# gem: GeM bid-result pages and bid documents

A family of the s1d-labs scrape pool. It fetches public pages of GeM's bid portal (bidplus.gem.gov.in) by GeM's internal bid id:

| Task | Page | Stored |
|---|---|---|
| `results` | `/bidding/bid/getBidResultView/<id>`: every bidder, offered make/model, technical result, price-stage quotes | one record per id (parsed, `gemresult.py`) + the raw pages of each queue item as one archive `<project>/results/<item>.tar.gz` in the family bucket |
| `pdfs` | `/showbidDocument/<id>`: the bid document | one tar per queue item `<project>/pdf/<item>.tar` (members `<id>.pdf`) in the family bucket + one record per id (archive, size, checksum) |

- GeM answers only from India: the projects use `geo="IN"`, so the work runs on the pool's India servers only.
- Pace: 0.1 s between requests per worker at all hours; failed requests are retried. At most 20 workers on the host; the hub's
  back-off applies on top (`gemcommon.py`).
- Personal data: result pages carry the buyer official's name, address, e-mail and phone. The parser never extracts them; raw pages
  stay in the private bucket; the saved test pages here have them removed.
- Pilot: Chhattisgarh state buyers' bids (`data/cg_pids.txt.gz`, 20,116 ids), done 2026-10-31. National result pages: `data/held_pids.txt.gz` (4.58M ids).

Setup: change `family.py`, then Actions -> setup. Tests: `python -m pytest tests`.
