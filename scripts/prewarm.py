"""Pre-warm the business-level caches (topics + brand voices + personas) for Odin clients.

Run this ahead of a demo so the Topics and Preferences steps are instant. It writes to the
same persistent cache the app reads (lib/cache.py), keyed identically, so a warmed business
shows a "Generated <timestamp>" state with no wait.

Usage:
    .venv/bin/python scripts/prewarm.py                 # all Odin clients, skip already-warm
    .venv/bin/python scripts/prewarm.py --force         # regenerate even if cached
    .venv/bin/python scripts/prewarm.py company-ihg-com company-grand-velas   # specific ids
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import cache, odin, preferences, topicgen  # noqa: E402

FORCE = "--force" in sys.argv
ONLY = [a for a in sys.argv[1:] if not a.startswith("-")]


def warm_client(c: dict) -> None:
    cid, name = c["id"], c["name"]
    scope = f"{cid}/primary"
    tkey = cache.key(cid, "create")
    pkey = cache.key(cid)

    have_topics = bool(cache.load("topics", tkey)[0])
    have_prefs = bool(cache.load("prefs", pkey)[0])
    if have_topics and have_prefs and not FORCE:
        print(f"  · {name}: already warm, skipping", flush=True)
        return

    t0 = time.time()
    bundle = odin.gather_grounding(scope, name, light=True)
    n_nodes = sum(len(v) for k, v in bundle.items() if isinstance(v, list) and not k.startswith("_"))
    print(f"  · {name}: grounding {n_nodes} nodes in {time.time()-t0:.0f}s", flush=True)
    if n_nodes == 0:
        print(f"    ! {name}: no grounding nodes — skipping", flush=True)
        return

    if FORCE or not have_topics:
        t = time.time()
        _, data = topicgen.generate_topics(business_id=cid, business_name=name, scope=scope,
                                           grounding_bundle=bundle, page_snapshot=None, n=15,
                                           model="haiku", use_cache=False)
        cache.save("topics", tkey, data)
        print(f"    ✓ topics: {len(data.get('opportunities', []))} in {time.time()-t:.0f}s", flush=True)

    if FORCE or not have_prefs:
        t = time.time()
        opts = preferences.generate_preferences(business_name=name, grounding_bundle=bundle, model="haiku")
        cache.save("prefs", pkey, opts)
        print(f"    ✓ prefs: {len(opts['brand_voices'])} voices / {len(opts['personas'])} personas "
              f"in {time.time()-t:.0f}s", flush=True)


def main() -> None:
    clients = odin.list_clients()
    if ONLY:
        clients = [c for c in clients if c["id"] in ONLY or c["name"] in ONLY]
    print(f"Pre-warming {len(clients)} client(s){' (force)' if FORCE else ''}…", flush=True)
    t0 = time.time()
    for i, c in enumerate(clients, 1):
        print(f"[{i}/{len(clients)}] {c['name']} ({c['id']})", flush=True)
        try:
            warm_client(c)
        except Exception as e:  # noqa: BLE001 — one client failing must not stop the batch
            print(f"    ! failed: {e}", flush=True)
    print(f"Done in {time.time()-t0:.0f}s.", flush=True)


if __name__ == "__main__":
    main()
