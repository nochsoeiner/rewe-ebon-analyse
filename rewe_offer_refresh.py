#!/usr/bin/env python3
"""Refresh REWE discounted catalogues and republish the local eBon report.

The catalogue requests contain only the configured market IDs and an offer
filter. Purchased names are compared locally after both catalogues arrive.
"""

import fcntl
import json
import os
import sqlite3
import tempfile
from pathlib import Path

import rewe_analyze
import rewe_shop


SNAPSHOT_PATH = rewe_analyze.DATA_DIR / "rewe_offer_snapshot.json"


def refresh() -> dict:
    with sqlite3.connect(f"file:{rewe_analyze.DB_PATH}?mode=ro", uri=True) as connection:
        snapshot = rewe_shop.offer_snapshot(connection)
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".rewe-offers-", dir=SNAPSHOT_PATH.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(snapshot, output, ensure_ascii=False, separators=(",", ":"))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, SNAPSHOT_PATH)
    finally:
        Path(temporary).unlink(missing_ok=True)
    with sqlite3.connect(f"file:{rewe_analyze.DB_PATH}?mode=ro", uri=True) as connection:
        rewe_analyze.generate_report(connection)
    return snapshot


if __name__ == "__main__":
    lock_path = rewe_analyze.DATA_DIR / "rewe_offer_refresh.lock"
    with lock_path.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("REWE-Angebotsabruf läuft bereits.")
            raise SystemExit(0)
        result = refresh()
        print("REWE-Angebote aktualisiert:", ", ".join(
            f"{channel} {sum(row['status'] == 'offer' for row in data['items'])} Treffer"
            for channel, data in result["channels"].items()))
