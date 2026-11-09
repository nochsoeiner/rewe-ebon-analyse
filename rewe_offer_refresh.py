#!/usr/bin/env python3
"""Refresh REWE discounted catalogues and republish the local eBon report.

The offer catalogue requests contain only the configured market IDs and an
offer filter; purchased names are compared locally. Every interrupted page run
is saved, so a run stopped by REWE's rate limit continues later where it
stopped.

Additionally, small batches of purchased names are looked up one by one in the
REWE product search to learn their product IDs (``rewe_product_map.json``).
This step does send these names to REWE, like the manual check in the local
app. Once an ID is known, the offer is recognised regardless of how the eBon
abbreviates the product.

Without ``--scheduled`` the catalogue is fetched now (continuing a saved run).
With ``--scheduled`` (LaunchAgent) it is fetched only when the current offer
week, starting Sunday 18:00 local time, has no complete catalogue yet; the
night runs then only continue the name lookups.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sqlite3
import sys
import tempfile
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

import rewe_analyze
import rewe_shop


SNAPSHOT_PATH = rewe_analyze.DATA_DIR / "rewe_offer_snapshot.json"
CATALOGUE_PATH = rewe_analyze.DATA_DIR / "rewe_offer_catalogue.json"
PROGRESS_PATH = rewe_analyze.DATA_DIR / "rewe_offer_progress.json"
PRODUCT_MAP_PATH = rewe_analyze.DATA_DIR / "rewe_product_map.json"

# Unattended runs are slow on purpose: few requests, long pauses after HTTP 429.
BACKGROUND_PACING = {"interval": 3.0, "retry_delays": (60, 300), "max_retry_after": 300}
DEFAULT_MAP_LIMIT = 60


def _write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.stem}-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(value, output, ensure_ascii=False, separators=(",", ":"))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _read_json(path: Path):
    try:
        value = json.loads(path.read_text("utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def _parse(value) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


def offer_week_start(now: datetime) -> datetime:
    """Most recent Sunday 18:00 in the local time of ``now``."""
    # Calculate in naive wall-clock time so a DST change keeps 18:00 at 18:00.
    local = now.astimezone().replace(tzinfo=None)
    start = local.replace(hour=18, minute=0, second=0, microsecond=0) - timedelta(days=(local.weekday() + 1) % 7)
    if start > local:
        start -= timedelta(days=7)
    return start.astimezone()


def load_catalogue() -> dict | None:
    catalogue = _read_json(CATALOGUE_PATH)
    if (not catalogue or _parse(catalogue.get("checkedAt")) is None or
            not isinstance(catalogue.get("channels"), dict) or
            any(not isinstance(catalogue["channels"].get(channel), list) for channel in rewe_shop.CHANNELS)):
        return None
    return catalogue


def load_product_map() -> dict:
    data = _read_json(PRODUCT_MAP_PATH) or {}
    channels = data.get("channels")
    if not isinstance(channels, dict):
        return {}
    return {channel: entries for channel, entries in channels.items()
            if channel in rewe_shop.CHANNELS and isinstance(entries, dict)}


def save_product_map(product_map: dict) -> None:
    _write_json(PRODUCT_MAP_PATH, {"version": 1, "channels": product_map})


def fetch_catalogue(now: datetime) -> dict:
    """Fetch both offer catalogues; raises ShopThrottled with the progress saved."""
    progress = _read_json(PROGRESS_PATH)
    started = _parse((progress or {}).get("startedAt"))
    if (progress is None or started is None or started < offer_week_start(now) or
            not isinstance(progress.get("channels"), dict)):
        progress = {"startedAt": now.isoformat(timespec="seconds"), "channels": {}}
    for channel in rewe_shop.CHANNELS:
        state = progress["channels"].get(channel) or {}
        if state.get("done"):
            continue

        def save(page_state, channel=channel):
            progress["channels"][channel] = {**page_state, "done": False}
            _write_json(PROGRESS_PATH, progress)

        offers = rewe_shop.discounted_products(channel, state, save)
        progress["channels"][channel] = {"done": True, "offers": offers}
        _write_json(PROGRESS_PATH, progress)
    catalogue = {"checkedAt": now.isoformat(timespec="seconds"),
                 "channels": {channel: progress["channels"][channel]["offers"]
                              for channel in rewe_shop.CHANNELS}}
    _write_json(CATALOGUE_PATH, catalogue)
    PROGRESS_PATH.unlink(missing_ok=True)
    return catalogue


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{rewe_analyze.DB_PATH}?mode=ro", uri=True)


def publish(catalogue: dict, product_map: dict) -> dict:
    with closing(_connect()) as connection:
        snapshot = rewe_shop.offer_snapshot(connection, catalogue, product_map)
    _write_json(SNAPSHOT_PATH, snapshot)
    with closing(_connect()) as connection:
        rewe_analyze.generate_report(connection)
    return snapshot


def run(scheduled: bool = False, map_limit: int = DEFAULT_MAP_LIMIT,
        now: datetime | None = None, log=print) -> dict:
    now = (now or datetime.now()).astimezone()
    catalogue = load_catalogue()
    product_map = load_product_map()
    fetched = throttled = False

    due = (not scheduled or catalogue is None or PROGRESS_PATH.exists() or
           _parse(catalogue["checkedAt"]) < offer_week_start(now))
    if due:
        try:
            catalogue = fetch_catalogue(now)
            fetched = True
        except rewe_shop.ShopThrottled as error:
            throttled = True
            progress = _read_json(PROGRESS_PATH) or {}
            pages = ", ".join(f"{channel} bis Seite {state.get('page', 1) - 1}/{state.get('totalPages', '?')}"
                              if not state.get("done") else f"{channel} vollständig"
                              for channel, state in progress.get("channels", {}).items())
            log(f"REWE bremst den Angebotsabruf ({error}); Fortsetzung beim nächsten Lauf"
                + (f" ({pages})." if pages else "."))

    mapping = {"lookedUp": 0, "mapped": 0, "paused": False}
    if not throttled and map_limit > 0:
        with closing(_connect()) as connection:
            candidates = rewe_shop.mapping_candidates(connection, product_map, now)
        mapping = rewe_shop.map_products(candidates, product_map, map_limit, now, on_item=save_product_map)
        mapping["open"] = max(0, len(candidates) - mapping["lookedUp"])
        log(f"Produktzuordnung: {mapping['lookedUp']} Namen gesucht, {mapping['mapped']} zugeordnet, "
            f"{mapping['open']} offen" + (" · REWE bremst, Fortsetzung beim nächsten Lauf." if mapping["paused"] else "."))

    snapshot = None
    if catalogue is not None and (fetched or mapping["lookedUp"] or not SNAPSHOT_PATH.exists()):
        snapshot = publish(catalogue, product_map)
        for channel, data in snapshot["channels"].items():
            counts = {}
            for row in data["items"]:
                key = row["status"] if row["status"] != "offer" else f"offer-{row.get('matchedBy')}"
                counts[key] = counts.get(key, 0) + 1
            log(f"{channel}: {data['catalogueOffers']} Angebote im Katalog · {len(data['items'])} gekaufte Artikel · "
                f"Angebot {counts.get('offer-id', 0)} per Produkt-ID + {counts.get('offer-name', 0)} per Name · "
                f"zugeordnet ohne Angebot {counts.get('nooffer', 0)} · ohne sichere Zuordnung "
                f"{counts.get('unmapped', 0)} · noch nicht gesucht {counts.get('pending', 0)}")
    return {"fetched": fetched, "throttled": throttled, "mapping": mapping, "snapshot": snapshot}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--scheduled", action="store_true",
                        help="Hintergrundlauf: Katalog nur bei fälliger Angebotswoche, langsame Abfragen")
    parser.add_argument("--map-limit", type=int, default=DEFAULT_MAP_LIMIT,
                        help=f"Höchstzahl der Namenssuchen in diesem Lauf (Standard {DEFAULT_MAP_LIMIT}, 0 = keine)")
    args = parser.parse_args(argv)
    if args.scheduled:
        rewe_shop.configure_pacing(**BACKGROUND_PACING)
    lock_path = rewe_analyze.DATA_DIR / "rewe_offer_refresh.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("REWE-Angebotsabruf läuft bereits.")
            return 0
        print(datetime.now().astimezone().isoformat(timespec="seconds"), "REWE-Angebotslauf",
              "(geplant)" if args.scheduled else "(manuell)")
        run(scheduled=args.scheduled, map_limit=max(0, args.map_limit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
