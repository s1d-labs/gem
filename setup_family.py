"""Put this family's projects in the pool. Run by the Setup workflow (GitHub Actions: the hub trusts this repo through its OIDC
token). Safe to run again: queue items that exist are kept."""
from scrape_hub_client import register_project, seed_queue, set_pool, set_probes

from family import FAMILY, PROBES, PROJECTS, bid_items, items

print("health checks:", set_probes(FAMILY, PROBES))
for p in PROJECTS:
    its = bid_items(p["list"]) if p.get("kind") == "bids" else items(p["list"])
    register_project(p["name"], title=p["title"], unit_label=p["unit_label"], record_label=p["record_label"],
                     expected_units=len(its), expected_records=sum(i["payload"]["expected"] for i in its))
    set_pool(p["name"], FAMILY, p["task"], target=p["target"], env=p["env"], probe=p["probe"], max_workers=p["max_workers"], geo=p["geo"])
    print(p["name"], "queue:", seed_queue(p["name"], its))
