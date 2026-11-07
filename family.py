"""What this family scrapes: GeM's public bid-result pages and bid documents, by GeM's internal bid id (portal_internal_id).

Queue items hold CHUNK ids each (one upload call per item). Id lists live in data/*.txt.gz, one id per line.
The site answers only from India (geo="IN"): the work runs on the pool's India servers only. GeM refuses foreign IPs, so a
health check run by the hub (in Germany) would always fail; like the family's other India-only peers, no probe is set.
Pilot: Chhattisgarh state buyers (20,116 bids), done and checked 2026-10-31. National: result pages of all other known bids
(data/held_pids.txt.gz, 4.58M), then their bid documents (gem-pdfs, about 620 GB; bucket cap raised to 1 TB).
Parsing (task pdfparse, project gem-pdf-parse, GitHub runners): its items carry presigned links to the stored tars, so they are
seeded from the investigation box (woodpecker investigation/gem_pdf_load.py --seed), not from this public repo.
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


def bid_items(name):
    """Items of CHUNK bid numbers for the lookup task."""
    xs = ids(name)
    return [{"key": f"{name}-{i // CHUNK:05d}", "payload": {"bids": xs[i:i + CHUNK], "expected": len(xs[i:i + CHUNK])}}
            for i in range(0, len(xs), CHUNK)]


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
     "unit_label": "chunk", "record_label": "bid", "list": "held_pids", "max_workers": 28},   # 30 India workers (6 per IP), 2026-11-01
    {"name": f"{FAMILY}-pdfs", "title": "GeM: bid documents of all known bids (outside the Chhattisgarh pilot)", "task": "pdfs",
     "unit_label": "chunk", "record_label": "document", "list": "held_pids", "max_workers": 28},
    {"name": f"{FAMILY}-results-retry", "title": "GeM: result pages that failed twice (GeM's daytime HTTP 500s), second pass", "task": "results",
     "unit_label": "chunk", "record_label": "bid", "list": "results_retry", "max_workers": 2},
    # bid numbers that archived government documents quote but our copies lack (s1d-labs/graph gaps/): number -> internal id
    {"name": f"{FAMILY}-archive-lookup", "title": "GeM: internal ids of bids quoted in archived documents", "task": "lookup",
     "unit_label": "chunk", "record_label": "bid", "list": "archive_bids", "max_workers": 2, "kind": "bids", "proxy": "IN"},
    # ... and their result pages and bid documents (ids from gem-archive-lookup, minus ids the national crawl already holds)
    {"name": f"{FAMILY}-archive-results", "title": "GeM: result pages of bids quoted in archived documents", "task": "results",
     "unit_label": "chunk", "record_label": "bid", "list": "archive_pids", "max_workers": 4, "proxy": "IN"},
    {"name": f"{FAMILY}-archive-pdfs", "title": "GeM: bid documents of bids quoted in archived documents", "task": "pdfs",
     "unit_label": "chunk", "record_label": "document", "list": "archive_pids", "max_workers": 4, "proxy": "IN"},
]
for p in PROJECTS:
    p.update(target=TARGET, env={}, geo="IN", probe=None)
    p.setdefault("proxy", "")   # "IN": GitHub runners may take the work too, through a borrowed Mumbai proxy (small queues
                                # otherwise wait behind the big India-server families: servers serve the most waiting first)

PROBES = []
