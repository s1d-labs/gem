"""What this family scrapes: GeM's public bid-result pages and bid documents, by GeM's internal bid id (portal_internal_id).

Queue items hold CHUNK ids each (one upload call per item). Id lists live in data/*.txt.gz, one id per line.
The site answers only from India (geo="IN"): the work runs on the pool's India servers only. GeM refuses foreign IPs, so a
health check run by the hub (in Germany) would always fail; like the family's other India-only peers, no probe is set.
Pilot: Chhattisgarh state buyers (20,116 bids), done and checked 2026-10-31. National: result pages of all other known bids
(data/held_pids.txt.gz, 4.58M); national bid documents get added when the bucket's cap is raised (about 620 GB).
"""
import gzip
import json
from pathlib import Path

HERE = Path(__file__).parent
FAMILY = json.loads((HERE / "scrape.json").read_text())["family"]
TARGET = "bidplus.gem.gov.in"
CHUNK = 200


def ids(name):
    with gzip.open(HERE / "data" / f"{name}.txt.gz", "rt") as f:
        return [l.strip() for l in f if l.strip()]


def items(name, expected=1):
    xs = ids(name)
    return [{"key": f"{name}-{i // CHUNK:05d}", "payload": {"ids": xs[i:i + CHUNK], "expected": len(xs[i:i + CHUNK]) * expected}}
            for i in range(0, len(xs), CHUNK)]


PROJECTS = [
    {"name": f"{FAMILY}-cg-results", "title": "GeM pilot: result pages of Chhattisgarh state bids", "task": "results",
     "unit_label": "chunk", "record_label": "bid", "list": "cg_pids", "max_workers": 8},
    {"name": f"{FAMILY}-cg-pdfs", "title": "GeM pilot: bid documents of Chhattisgarh state bids", "task": "pdfs",
     "unit_label": "chunk", "record_label": "document", "list": "cg_pids", "max_workers": 8},
    {"name": f"{FAMILY}-cg-pdfs-retry", "title": "GeM pilot: bid documents that came back empty, second try", "task": "pdfs",
     "unit_label": "chunk", "record_label": "document", "list": "cg_pdf_retry", "max_workers": 2},
    # national: result pages of every other bid id in the Woodpecker copy (4.58M); bid documents follow once the bucket cap allows
    {"name": f"{FAMILY}-results", "title": "GeM: result pages of all known bids (outside the Chhattisgarh pilot)", "task": "results",
     "unit_label": "chunk", "record_label": "bid", "list": "held_pids", "max_workers": 16},   # ramping 12 -> 16 -> 20 (owner: aim 40 bids/s)
]
for p in PROJECTS:
    p.update(target=TARGET, env={}, geo="IN", probe=None)

PROBES = []
