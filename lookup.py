"""Task `lookup`: GeM bid numbers -> GeM's internal bid id, through the public "All bids" search on bidplus (no login, no
captcha). One record per bid number: the internal id (pid) and what the search shows (category, quantity, dates, status).
The found ids then go to the family's `results` and `pdfs` tasks like any other id list.

Input: bid numbers that archived government documents quote but our copies do not hold (s1d-labs/graph gaps/).
Outcomes per bid: found (record with pid); not found (record with found=false: the search knows no such bid); or a fetch
failure (reported with hub.failure("lookup", bid) and retried later).
"""
import json, os, re, time

import requests
from scrape_hub_client import HubClient

import gemcommon as g

PROJECT = os.environ["SCRAPE_POOL_PROJECT"]
KEEP = ("b_category_name", "b_total_quantity", "b_status", "b_bid_type", "b_type", "b_bid_to_ra", "b_eval_type",
        "final_start_date_sort", "final_end_date_sort", "ba_official_details_minName", "ba_official_details_deptName")


class Search:
    """The All-bids page hands out a CSRF token with its session cookie; the search POST needs both."""
    def __init__(self, hub):
        self.hub, self.s, self.token, self.used = hub, g.session(), None, 0

    def refresh(self):
        st, body = g.get(self.hub, self.s, f"{g.HOST}/all-bids")
        m = re.search(rb'csrf_bd_gem_nk["\']?\s*[:=]\s*["\']([0-9a-f]{20,})', body or b"") or \
            re.search(rb'name="csrf_bd_gem_nk" value="([0-9a-f]+)"', body or b"")
        self.token = m.group(1).decode() if m else None
        self.used = 0
        return self.token is not None

    def find(self, bid):
        """-> ("ok", doc | None) or ("fail", reason)."""
        if (self.token is None or self.used >= 500) and not self.refresh():
            return "fail", "no CSRF token on the All bids page"
        payload = {"param": {"searchBid": bid, "searchType": "fullText"},
                   "filter": {"bidStatusType": "all", "byType": "all", "highBidValue": "",
                              "byEndDate": {"from": "", "to": ""}, "sort": "Bid-End-Date-Oldest"}}
        t = time.time()
        try:
            r = self.s.post(f"{g.HOST}/all-bids-data", timeout=60,
                            data={"payload": json.dumps(payload), "csrf_bd_gem_nk": self.token},
                            headers={"X-Requested-With": "XMLHttpRequest", "Referer": f"{g.HOST}/all-bids"})
        except requests.RequestException:
            self.hub.metric("http_error"); self.hub.error()
            return "fail", "connection error"
        self.hub.metric("n_http"); self.hub.metric("t_http_s", time.time() - t)
        self.used += 1
        if r.status_code == 404 and b"No data found" in r.content[:200]:   # GeM's search answers 404 for an unknown bid
            self.hub.metric("not_found")
            return "ok", None
        if r.status_code != 200:
            self.hub.metric(f"http_{r.status_code}")
            if r.status_code in (403, 429, 503):
                self.hub.block()
            self.token = None                                  # a stale token answers with an error page: fetch a new one
            return "fail", f"status {r.status_code}"
        try:
            docs = r.json()["response"]["response"]["docs"]
        except (ValueError, KeyError, TypeError):
            self.token = None
            return "fail", "not a search answer"
        for d in docs:
            if bid in (d.get("b_bid_number") or []):
                return "ok", d
        return "ok", None


def main():
    hub = HubClient(PROJECT, job_index=int(os.environ.get("SCRAPE_JOB_INDEX", 0)), total_jobs=int(os.environ.get("SCRAPE_TOTAL_JOBS", 1)))
    search, end = Search(hub), g.deadline()
    try:
        while time.time() < end and not g.STOP["now"]:
            if hub.settings.get("paused"):
                time.sleep(30); continue
            got = hub.claim(1, steal=True, retry_failed=True)
            if not got:
                break
            item = got[0]
            n_ok = n_fail = 0
            stopped = False
            for bid in item["payload"]["bids"]:
                if g.STOP["now"] or time.time() >= end:
                    stopped = True; break
                state, doc = search.find(bid)
                if state == "fail":
                    time.sleep(5)
                    state, doc = search.find(bid)
                if state == "fail":
                    hub.failure("lookup", bid, doc); n_fail += 1
                elif doc is None:
                    hub.record(bid, {"bid_number": bid, "found": False}); n_ok += 1
                else:
                    rec = {"bid_number": bid, "found": True, "pid": str(doc.get("id") or (doc.get("b_id") or [None])[0])}
                    rec.update({k: (v[0] if isinstance(v, list) and len(v) == 1 else v) for k, v in doc.items() if k in KEEP})
                    hub.record(bid, rec); n_ok += 1
                time.sleep(g.gap(hub))
            if stopped:
                hub.complete([item["key"]], "failed", error="stopped before the end of the item (time up)")
                break
            hub.complete([item["key"]], "done", fetched=n_ok)       # failed bids are retried through hub.failure, as in results.py
            hub.metric("ids_failed", n_fail)
        hub.close()
    except BaseException as e:
        hub.close("failed", f"{type(e).__name__}: {e}"[:200])
        raise


if __name__ == "__main__":
    main()
