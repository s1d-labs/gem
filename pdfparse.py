"""Task `pdfparse`: parse the bid documents the `pdfs` task stored, on GitHub's runners (pdftotext is CPU-bound; the pool has the
CPUs). Each queue item names one stored tar and carries a presigned link to it (made on the hub's box, one file, expiring), so no
storage key ever reaches a runner. The parsed rows (gemparse.pdf: header fields, items, consignees as PIN + quantity, buyer terms,
spec text, links; never officials' names or contacts) go back to the family's bucket as <project>/parsed/<item key>.json.gz,
{"src": <tar key>, "rows": [[pid, parsed], ...]}; the investigation box loads them into its database. No records: the hub only
tracks the items.
"""
import gzip, json, os, resource, shutil, sys, tarfile, time, io
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool

import requests
from scrape_hub_client import HubClient

import gemcommon as g
from gemparse import pdf

PROJECT = os.environ["SCRAPE_POOL_PROJECT"]
PROCS = max(1, (os.cpu_count() or 2) // 2)        # the runner starts two task processes per job
MEM_CAP = 2 << 30                                  # per parse process: old pypdf versions balloon on some malformed annotations


def cap():
    resource.setrlimit(resource.RLIMIT_AS, (MEM_CAP, MEM_CAP))


def one(arg):
    pid, data = arg
    try:
        return pid, pdf.parse(data)
    except Exception as e:
        return pid, {"error": repr(e)}


def parse_tar(ex, data):
    with tarfile.open(fileobj=io.BytesIO(data)) as t:
        members = [(m.name[:-4], t.extractfile(m).read()) for m in t.getmembers() if m.isfile() and m.name.endswith(".pdf")]
    return list(ex.map(one, members, chunksize=2))


def main():
    hub = HubClient(PROJECT, job_index=int(os.environ.get("SCRAPE_JOB_INDEX", 0)), total_jobs=int(os.environ.get("SCRAPE_TOTAL_JOBS", 1)))
    if not shutil.which("pdftotext"):
        hub.close("failed", "pdftotext missing (poppler-utils): this task runs on GitHub runners, where setup installs it")
        return 1
    end, s = g.deadline(), requests.Session()
    ex = ProcessPoolExecutor(PROCS, initializer=cap)
    try:
        while time.time() < end - 180 and not g.STOP["now"]:
            if hub.settings.get("paused"):
                time.sleep(30); continue
            got = hub.claim(1, steal=True, retry_failed=True)
            if not got:
                break
            item = got[0]
            try:
                r = s.get(item["payload"]["url"], timeout=300)
                r.raise_for_status()
                try:
                    rows = parse_tar(ex, r.content)
                except BrokenProcessPool:                 # a parse process died: new pool, this item once more
                    ex.shutdown(wait=False, cancel_futures=True)
                    ex = ProcessPoolExecutor(PROCS, initializer=cap)
                    rows = parse_tar(ex, r.content)
            except Exception as e:
                hub.complete([item["key"]], "failed", error=f"{type(e).__name__}: {e}"[:200])
                continue
            body = gzip.compress(json.dumps({"src": item["payload"]["src"], "rows": rows}).encode(), 6)
            hub.upload_many([(f"parsed/{item['key']}.json.gz", body, "application/gzip")])
            hub.metric("pdfs_parsed", len(rows))
            hub.complete([item["key"]], "done", fetched=len(rows))
        hub.close()
    except BaseException as e:
        hub.close("failed", f"{type(e).__name__}: {e}"[:200]); raise
    finally:
        ex.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    sys.exit(main())
