import copy
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import rewe_analyze
import rewe_offer_refresh
from rewe_shop import load_offer_snapshot


def snapshot():
    return {"checkedAt": "2026-09-28T06:00:00+00:00", "channels": {
        channel: {"catalogueOffers": 1, "items": [
            {"name": "Testartikel", "status": "offer", "validUntil": "2026-10-03T00:00:00CEST"}
        ]} for channel in ("market", "online")}}


class ReweOfferStateTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "snapshot.json"

    def write(self, value):
        self.path.write_text(json.dumps(value), encoding="utf-8")

    def test_old_complete_snapshot_still_reaches_the_report(self):
        data = snapshot()
        self.write(data)
        self.assertEqual(load_offer_snapshot(self.path), data)

    def test_zero_offers_is_a_valid_snapshot(self):
        data = snapshot()
        for channel in data["channels"].values():
            channel.update(items=[], catalogueOffers=0)
        self.write(data)
        self.assertEqual(load_offer_snapshot(self.path), data)

    def test_malformed_and_incomplete_snapshots_are_rejected(self):
        mutations = [
            lambda s: s["channels"].pop("online"),
            lambda s: s["channels"]["market"].update(items=None),
            lambda s: s["channels"]["online"].update(items=[None]),
            lambda s: s["channels"]["online"].update(catalogueOffers=-1),
            lambda s: s["channels"]["online"].update(catalogueOffers=True),
            lambda s: s.update(checkedAt="2026-09-28T06:00:00"),
        ]
        for mutate in mutations:
            data = copy.deepcopy(snapshot())
            mutate(data)
            self.write(data)
            with self.subTest(data=data):
                self.assertIsNone(load_offer_snapshot(self.path))
        self.write([])
        self.assertIsNone(load_offer_snapshot(self.path))
        self.path.write_text("{", encoding="utf-8")
        self.assertIsNone(load_offer_snapshot(self.path))
        self.path.unlink()
        self.assertIsNone(load_offer_snapshot(self.path))

    def test_failed_catalogue_keeps_snapshot_and_does_not_regenerate_report(self):
        self.write(snapshot())
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        database = Path(self.temporary.name) / "rewe.db"
        sqlite3.connect(database).close()
        with patch.object(rewe_offer_refresh, "SNAPSHOT_PATH", self.path), \
                patch.object(rewe_analyze, "DB_PATH", database), \
                patch("rewe_offer_refresh.rewe_shop.offer_snapshot", side_effect=OSError("catalogue failed")), \
                patch.object(rewe_analyze, "generate_report") as report:
            with self.assertRaises(OSError):
                rewe_offer_refresh.refresh()
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)
        report.assert_not_called()


if __name__ == "__main__":
    unittest.main()
