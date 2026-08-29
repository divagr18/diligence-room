"""Poll the deployed dashboard's findings endpoint and stamp when each appears.

Used to time beat 3: the live replay runs far longer than the beat's budget, so
the take has to start where findings actually start landing.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request

URL = (
    sys.argv[1]
    if len(sys.argv) > 1
    else ("https://diligence-room-dashboard-378831539922.us-central1.run.app/api/findings")
)
DURATION = float(sys.argv[2]) if len(sys.argv) > 2 else 300.0

start = time.monotonic()
seen: dict[str, float] = {}
while (elapsed := time.monotonic() - start) < DURATION:
    try:
        with urllib.request.urlopen(URL, timeout=10) as resp:
            items = json.load(resp)
    except Exception as exc:  # noqa: BLE001 - polling is best-effort
        print(f"{elapsed:7.1f}s  ERROR {exc}", flush=True)
        time.sleep(3)
        continue
    for item in items:
        fid = item.get("finding_id") or item.get("id") or json.dumps(item, sort_keys=True)[:40]
        if fid not in seen:
            seen[fid] = elapsed
            print(
                f"{elapsed:7.1f}s  +FINDING #{len(seen)} "
                f"{item.get('severity', '?')} {item.get('title', '')[:60]}",
                flush=True,
            )
    time.sleep(3)

print(f"\ntotal findings: {len(seen)}")
for fid, t in sorted(seen.items(), key=lambda kv: kv[1]):
    print(f"  {t:7.1f}s  {fid}")
