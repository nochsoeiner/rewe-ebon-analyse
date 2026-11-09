import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import rewe_analyze
import rewe_offer_refresh
import rewe_shop
from rewe_shop import ShopThrottled


def raw_product(name, product_id, price=199, regular=249):
    pricing = {"currentRetailPrice": price,
               "discount": {"regularPrice": regular, "discountRate": 20, "validTo": "2026-11-14"}}
    return {"id": product_id, "productName": name,
            "_embedded": {"articles": [{"_embedded": {"listing": {"pricing": pricing}}}]}}


def offer(name, product_id):
    return {**rewe_shop._product_data(raw_product(name, product_id)), "status": "offer"}


def database(path, names):
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE receipts(id INTEGER, date TEXT, receipt_type TEXT, market_id TEXT);
        CREATE TABLE items(id INTEGER, receipt_id INTEGER, name TEXT, unit_price REAL);
        INSERT INTO receipts VALUES (1,'2026-11-01','ebon','5775'),(2,'2026-11-02','shop',NULL);
    """)
    for index, (receipt, name) in enumerate(names, 1):
        connection.execute("INSERT INTO items VALUES (?,?,?,1.0)", (index, receipt, name))
    connection.commit()
    return connection


NOW = datetime(2026, 11, 10, 3, 0, tzinfo=timezone.utc)


class MatchingTest(unittest.TestCase):
    def test_receipt_spelling_of_umlauts_and_sizes(self):
        self.assertEqual(rewe_shop.normalize("MUELLER"), rewe_shop.normalize("Müller"))
        self.assertEqual(rewe_shop.normalize("COCA COLA 1,0L"), rewe_shop.normalize("Coca-Cola 1 l"))
        self.assertEqual(rewe_shop.normalize("H-Milch 3,5%"), "h milch 3 5")
        self.assertIsNotNone(rewe_shop.choose_product("MUELLER MILCHREIS", [
            raw_product("Müller Müllermilch Milchreis Klassik 200g", "1")]))

    def test_product_id_beats_name_and_reports_mapped_items_without_offer(self):
        with tempfile.TemporaryDirectory() as temporary:
            connection = database(Path(temporary) / "db", [
                (1, "KERRYG.BUTT."), (1, "JA H-MILCH 3,5%"), (1, "UNBEK.ART"), (1, "GESUCHT OHNE ID")])
            catalogue = {"checkedAt": NOW.isoformat(), "channels": {
                "market": [offer("Kerrygold Original Irische Butter 250g", "77"), offer("ja! H-Milch 3,5% 1l", "88")],
                "online": []}}
            product_map = {"market": {
                "KERRYG.BUTT.": {"productId": "77", "title": "Kerrygold", "checkedAt": NOW.isoformat()},
                "UNBEK.ART": {"productId": "99", "title": "Unbekannt", "checkedAt": NOW.isoformat()},
                "GESUCHT OHNE ID": {"productId": None, "title": None, "checkedAt": NOW.isoformat()}}}
            result = rewe_shop.offer_snapshot(connection, catalogue, product_map)
            connection.close()
        rows = {row["name"]: row for row in result["channels"]["market"]["items"]}
        self.assertEqual((rows["KERRYG.BUTT."]["status"], rows["KERRYG.BUTT."]["matchedBy"]), ("offer", "id"))
        self.assertEqual(rows["KERRYG.BUTT."]["price"], 1.99)
        self.assertEqual((rows["JA H-MILCH 3,5%"]["status"], rows["JA H-MILCH 3,5%"]["matchedBy"]), ("offer", "name"))
        self.assertEqual(rows["UNBEK.ART"]["status"], "nooffer")
        self.assertEqual(rows["GESUCHT OHNE ID"]["status"], "unmapped")
        self.assertEqual(result["checkedAt"], NOW.isoformat())


class OfferPagesTest(unittest.TestCase):
    def fake_page(self, fail_on=None):
        def page(parameters, _channel):
            if parameters["page"] == fail_on:
                raise ShopThrottled(429)
            number = parameters["page"]
            return {"pagination": {"page": number, "totalPages": 3},
                    "search": {"selectedFacets": {"attribute": ["discounted"]}},
                    "_embedded": {"products": [raw_product(f"Produkt {number}", str(number))]}}
        return page

    def test_interrupted_pages_resume_without_repeating(self):
        saved = []
        with patch("rewe_shop._catalogue_page", side_effect=self.fake_page(fail_on=3)):
            with self.assertRaises(ShopThrottled):
                rewe_shop.discounted_products("market", None, saved.append)
        self.assertEqual(saved[-1]["page"], 3)
        requested = []
        def page(parameters, channel):
            requested.append(parameters["page"])
            return self.fake_page()(parameters, channel)
        with patch("rewe_shop._catalogue_page", side_effect=page):
            offers = rewe_shop.discounted_products("market", saved[-1])
        self.assertEqual(requested, [3])
        self.assertEqual([row["productId"] for row in offers], ["1", "2", "3"])


class MappingTest(unittest.TestCase):
    def test_candidates_skip_known_ids_and_recent_misses_and_alternate_channels(self):
        with tempfile.TemporaryDirectory() as temporary:
            connection = database(Path(temporary) / "db", [
                (1, "A1"), (1, "A1"), (1, "A2"), (1, "A3"), (1, "A4"), (2, "B1")])
            product_map = {"market": {
                "A2": {"productId": "5", "checkedAt": NOW.isoformat()},
                "A3": {"productId": None, "checkedAt": (NOW - timedelta(days=2)).isoformat()},
                "A4": {"productId": None, "checkedAt": (NOW - timedelta(days=40)).isoformat()}}}
            candidates = rewe_shop.mapping_candidates(connection, product_map, NOW)
            connection.close()
        self.assertEqual([(channel, item["name"]) for channel, item in candidates],
                         [("market", "A1"), ("online", "B1"), ("market", "A4")])

    def test_throttle_keeps_completed_lookups(self):
        candidates = [("market", {"name": "Kerrygold Butter 250g"}), ("market", {"name": "Zweiter Artikel"}),
                      ("online", {"name": "Dritter Artikel"})]
        def fake_search(query, _channel):
            if query == "Zweiter Artikel":
                raise ShopThrottled(429)
            return [raw_product("Kerrygold Butter 250g", "42")]
        product_map = {}
        result = rewe_shop.map_products(candidates, product_map, 10, NOW, fake_search)
        self.assertEqual(result, {"lookedUp": 1, "mapped": 1, "paused": True})
        self.assertEqual(product_map["market"]["Kerrygold Butter 250g"]["productId"], "42")

    def test_search_without_secure_hit_is_remembered_but_errors_are_retried(self):
        candidates = [("market", {"name": "Unklarer Artikel"}), ("market", {"name": "Fehler Artikel"})]
        def fake_search(query, _channel):
            if query.startswith("Fehler"):
                raise OSError("timeout")
            return []
        product_map = {}
        rewe_shop.map_products(candidates, product_map, 10, NOW, fake_search)
        self.assertEqual(list(product_map["market"]), ["Unklarer Artikel"])
        self.assertIsNone(product_map["market"]["Unklarer Artikel"]["productId"])


class RefreshRunTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        database(self.directory / "rewe.db", [(1, "Kerrygold Butter 250g")]).close()
        for name, value in (("SNAPSHOT_PATH", "snapshot.json"), ("CATALOGUE_PATH", "catalogue.json"),
                            ("PROGRESS_PATH", "progress.json"), ("PRODUCT_MAP_PATH", "map.json")):
            patcher = patch.object(rewe_offer_refresh, name, self.directory / value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for patcher in (patch.object(rewe_analyze, "DB_PATH", self.directory / "rewe.db"),
                        patch.object(rewe_analyze, "generate_report")):
            self.report = patcher.start()
            self.addCleanup(patcher.stop)
        self.messages = []

    def page(self, fail_on=None, requested=None):
        def page(parameters, channel):
            if requested is not None:
                requested.append((channel, parameters["page"]))
            if (channel, parameters["page"]) == fail_on:
                raise ShopThrottled(429)
            return {"pagination": {"page": parameters["page"], "totalPages": 2},
                    "search": {"selectedFacets": {"attribute": ["discounted"]}},
                    "_embedded": {"products": [raw_product("Kerrygold Butter 250g", f"{channel}{parameters['page']}")]}}
        return page

    def test_throttled_catalogue_is_continued_by_the_next_night_run(self):
        with patch("rewe_shop._catalogue_page", side_effect=self.page(fail_on=("online", 2))):
            first = rewe_offer_refresh.run(scheduled=True, map_limit=0, now=NOW, log=self.messages.append)
        self.assertTrue(first["throttled"])
        self.assertFalse((self.directory / "snapshot.json").exists())
        self.report.assert_not_called()
        progress = json.loads((self.directory / "progress.json").read_text())
        self.assertTrue(progress["channels"]["market"]["done"])
        requested = []
        with patch("rewe_shop._catalogue_page", side_effect=self.page(requested=requested)):
            second = rewe_offer_refresh.run(scheduled=True, map_limit=0, now=NOW + timedelta(hours=1),
                                            log=self.messages.append)
        self.assertEqual(requested, [("online", 2)])
        self.assertTrue(second["fetched"])
        self.assertFalse((self.directory / "progress.json").exists())
        self.assertEqual(second["snapshot"]["checkedAt"], (NOW + timedelta(hours=1)).astimezone().isoformat(timespec="seconds"))
        self.report.assert_called_once()

    def test_night_run_without_due_catalogue_only_maps_names(self):
        catalogue = {"checkedAt": NOW.astimezone().isoformat(), "channels": {
            "market": [offer("Kerrygold Original Irische Butter 250g", "42")], "online": []}}
        (self.directory / "catalogue.json").write_text(json.dumps(catalogue))
        (self.directory / "snapshot.json").write_text("{}")
        with patch("rewe_shop._catalogue_page", side_effect=AssertionError("no catalogue request")), \
                patch("rewe_shop.search", return_value=[raw_product("Kerrygold Original Irische Butter 250g", "42")]):
            result = rewe_offer_refresh.run(scheduled=True, now=NOW + timedelta(hours=2), log=self.messages.append)
        self.assertFalse(result["fetched"])
        row = result["snapshot"]["channels"]["market"]["items"][0]
        self.assertEqual((row["status"], row["matchedBy"], row["productId"]), ("offer", "id", "42"))
        stored = json.loads((self.directory / "map.json").read_text())
        self.assertEqual(stored["channels"]["market"]["Kerrygold Butter 250g"]["productId"], "42")

    def test_offer_week_starts_sunday_evening(self):
        start = rewe_offer_refresh.offer_week_start(datetime(2026, 11, 10, 12, 0).astimezone())
        self.assertEqual((start.weekday(), start.hour, start.day), (6, 18, 8))
        sunday_noon = rewe_offer_refresh.offer_week_start(datetime(2026, 11, 15, 12, 0).astimezone())
        self.assertEqual(sunday_noon.day, 8)


if __name__ == "__main__":
    unittest.main()
