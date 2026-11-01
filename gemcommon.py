"""Shared fetch loop for GeM tasks: polite pacing by India time of day, the hub's metrics and back-off, deadline and SIGINT.

Pacing: 0.1 s between requests per worker at all hours (owner, 2026-11-01); failed requests are retried (once after 5 s in
the task, then the item/id is retried later). The hub's delay_ms (its automatic back-off), if larger, wins.
"""
import datetime, os, signal, time

import requests

HOST = os.environ.get("GEM_HOST", "https://bidplus.gem.gov.in")   # override only for local tests
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
NIGHT_GAP, DAY_GAP = 0.1, 0.1
STOP = {"now": False}
signal.signal(signal.SIGINT, lambda *a: STOP.update(now=True))


def gap(hub):
    h = datetime.datetime.now(IST).hour
    own = DAY_GAP if 10 <= h < 18 else NIGHT_GAP
    return max(own, (hub.settings.get("delay_ms") or 0) / 1000)


class Pace:
    """Seconds per id, measured; fits(n) = whether n more ids can finish (with uploads) before the run's deadline."""
    def __init__(self, end):
        self.end, self.n, self.t = end, 0, 0.0

    def add(self, seconds):
        self.n += 1; self.t += seconds

    def per_id(self, hub):
        return self.t / self.n if self.n >= 20 else gap(hub) + 1.0

    def fits(self, hub, n):
        return time.time() + n * self.per_id(hub) * 1.15 + 45 < self.end


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
