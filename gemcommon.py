"""Shared fetch loop for GeM tasks: polite pacing by India time of day, the hub's metrics and back-off, deadline and SIGINT.

Pacing (measured 2026-10-28 from the India VPS): GeM answered flat to 20 req/s in the early morning, but at midday it returns
about 10% HTTP 500 at any rate. So per worker: NIGHT_GAP between requests outside 10:00-18:00 IST (about 2.5 req/s per worker,
about 20 req/s for 8 workers), DAY_GAP inside it (about 0.5 req/s per worker). The hub's delay_ms, if larger, wins.
"""
import datetime, os, signal, time

import requests

HOST = os.environ.get("GEM_HOST", "https://bidplus.gem.gov.in")   # override only for local tests
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
NIGHT_GAP, DAY_GAP = 0.1, 1.7
STOP = {"now": False}
signal.signal(signal.SIGINT, lambda *a: STOP.update(now=True))


def gap(hub):
    h = datetime.datetime.now(IST).hour
    own = DAY_GAP if 10 <= h < 18 else NIGHT_GAP
    return max(own, (hub.settings.get("delay_ms") or 0) / 1000)


def deadline():
    return time.time() + float(os.environ.get("SCRAPE_MAX_HOURS", "1")) * 3600 - 120


def session():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (compatible; s1d-labs scrape pool)"
    return s


def get(hub, s, url):
    """-> (status, bytes) or (None, b"") on a connection error. Never follows redirects (a 307 on a result page means the bid
    has no public result). Reports n_http / t_http_s / http_<code> / http_error and the hub's block/error counters."""
    t = time.time()
    try:
        r = s.get(url, timeout=60, allow_redirects=False)
    except requests.RequestException:
        hub.metric("http_error"); hub.error()
        return None, b""
    hub.metric("n_http"); hub.metric("t_http_s", time.time() - t)
    if r.status_code != 200:
        hub.metric(f"http_{r.status_code}")
        if r.status_code in (403, 429, 503):
            hub.block()
        elif r.status_code >= 500:
            hub.error()
    return r.status_code, r.content
