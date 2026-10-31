"""Task `results`: for each GeM bid id in the claimed item, fetch the public bid-result page, store the parsed bidders (one record
per bid id) and the raw page (gzip) in the family's bucket at <project>/results/<id>.html.gz.

Outcomes per id: parsed result; no public result (307 to GeM's newer evaluation page, which needs a session); blank template
(the id is not a public bid); or a fetch failure (5xx / empty / connection), retried once after a pause and otherwise reported
with hub.failure("result", id) so it can be retried later without re-fetching the rest of the item.
"""
import gzip, os, sys, time

from scrape_hub_client import HubClient

import gemcommon as g
from gemresult import parse

PROJECT = os.environ["SCRAPE_POOL_PROJECT"]


def fetch_one(hub, s, pid):
    for attempt in (1, 2):
        st, body = g.get(hub, s, f"{g.HOST}/bidding/bid/getBidResultView/{pid}")
        if st in (301, 302, 303, 307, 308):
            return {"public": False, "reason": f"redirect {st} to the evaluation page (needs a session)"}, None
        if st == 200 and len(body) > 1000:
            return None, body
        time.sleep(5 if attempt == 1 else 0)
    return "fail", f"status {st}, {len(body)} bytes"


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
            files, n_ok, n_fail, stopped = [], 0, 0, False
            for pid in item["payload"]["ids"]:
                if g.STOP["now"] or time.time() >= end:
                    stopped = True; break
                rec, body = fetch_one(hub, s, pid)
                if rec == "fail":
                    hub.failure("result", pid, body); n_fail += 1
                elif body is None:
                    hub.record(pid, {"pid": pid, **rec}); n_ok += 1
                else:
                    d = parse(body.decode("utf-8", "ignore"))
                    d["pid"] = pid
                    d["public"] = d["bid_number"] is not None
                    if not d["public"]:
                        d["reason"] = ("blank template: not a public bid id" if d["blank_template"]
                                       else "no result on this page (e.g. an old-style reverse auction, GEM/yyyy/RA/n)")
                    hub.record(pid, d); n_ok += 1
                    if d["public"]:
                        files.append((f"results/{pid}.html.gz", gzip.compress(body, 6), "application/gzip"))
                time.sleep(g.gap(hub))
            if files:
                hub.upload_many(files)
            if stopped:
                hub.complete([item["key"]], "failed", error="stopped before the end of the item (time up)")
                break
            hub.complete([item["key"]], "done", fetched=n_ok)
            hub.metric("ids_failed", n_fail)
        hub.close()
    except BaseException as e:
        hub.close("failed", f"{type(e).__name__}: {e}"[:200]); raise


if __name__ == "__main__":
    sys.exit(main())
