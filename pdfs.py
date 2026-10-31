"""Task `pdfs`: for each GeM bid id in the claimed item, fetch the bid document (showbidDocument/<id>) and store it in the family's
bucket at <project>/pdf/<id>.pdf; one record per id with its size and checksum. The PDFs are parsed later, off the pool.

A 200 with an empty body or a 5xx is retried once after a pause; still failing -> hub.failure("pdf", id) (GeM serves some documents
only intermittently, and none for ids that are not public bids).
"""
import os, sys, time

from scrape_hub_client import HubClient

import gemcommon as g

PROJECT = os.environ["SCRAPE_POOL_PROJECT"]


def fetch_one(hub, s, pid):
    for attempt in (1, 2):
        st, body = g.get(hub, s, f"{g.HOST}/showbidDocument/{pid}")
        if st == 200 and body[:4] == b"%PDF":
            return body, None
        time.sleep(5 if attempt == 1 else 0)
    return None, f"status {st}, {len(body)} bytes" + ("" if not body else f", starts {body[:8]!r}")


def main():
    hub = HubClient(PROJECT, job_index=int(os.environ.get("SCRAPE_JOB_INDEX", 0)), total_jobs=int(os.environ.get("SCRAPE_TOTAL_JOBS", 1)))
    s, end = g.session(), g.deadline()
    try:
        while time.time() < end and not g.STOP["now"]:
            if hub.settings.get("paused"):
                time.sleep(30); continue
            got = hub.claim(1, steal=True, retry_failed=True)
            if not got:
                break
            item = got[0]
            files, stopped = [], False
            for pid in item["payload"]["ids"]:
                if g.STOP["now"] or time.time() >= end:
                    stopped = True; break
                body, why = fetch_one(hub, s, pid)
                if body is None:
                    hub.failure("pdf", pid, why)
                else:
                    files.append((f"pdf/{pid}.pdf", body, "application/pdf"))
                time.sleep(g.gap(hub))
            n = 0
            for i in range(0, len(files), 100):            # about 11 MB per upload call
                for f, res in zip(files[i:i + 100], hub.upload_many(files[i:i + 100])):
                    pid = f[0].split("/")[-1][:-4]
                    hub.record(pid, {"pid": pid, "path": res["path"], "bytes": res["bytes"], "sha256": res["sha256"]}); n += 1
            if stopped:
                hub.complete([item["key"]], "failed", error="stopped before the end of the item (time up)")
                break
            hub.complete([item["key"]], "done", fetched=n)
        hub.close()
    except BaseException as e:
        hub.close("failed", f"{type(e).__name__}: {e}"[:200]); raise


if __name__ == "__main__":
    sys.exit(main())
