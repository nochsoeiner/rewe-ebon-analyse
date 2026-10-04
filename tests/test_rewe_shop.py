import sqlite3
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from rewe_shop import ShopThrottled, check_items, choose_product, discounted_products, purchased_items, search


def product(name, product_id="123", price=199, regular=None):
    pricing = {"currentRetailPrice": price}
    if regular is not None:
        pricing["discount"] = {"regularPrice": regular, "discountRate": 20, "validTo": "2026-10-03T00:00:00CEST"}
    return {"id": product_id, "productName": name,
            "_embedded": {"articles": [{"_embedded": {"listing": {"pricing": pricing}}}]}}


class ReweShopTest(unittest.TestCase):
    def test_only_unambiguous_product_is_matched(self):
        self.assertEqual(choose_product("Dallmayr Prodomo 500g", [product("Dallmayr Prodomo 500g")])["id"], "123")
        self.assertEqual(choose_product("DALLM PRODOMO 500G", [product("Dallmayr Prodomo 500g")])["id"], "123")
        self.assertEqual(choose_product("DALLM PRODOMO 500G", [
            product("Dallmayr Prodomo 500g"), product("Dallmayr Prodomo naturmild 500g", "456")])["id"], "123")
        self.assertIsNone(choose_product("Dallmayr Prodomo", [
            product("Dallmayr Prodomo 500g"), product("Dallmayr Prodomo naturmild 500g", "456")]))
        self.assertIsNone(choose_product("Milch", [product("Haltbare Milch 1l")]))

    def test_offer_and_known_unavailable_are_separate(self):
        items = [{"name": "Dallmayr Prodomo 500g", "purchases": 4, "lastPrice": 9.99, "minPrice": 6.99},
                 {"name": "REWE Bio Joghurt 500g", "purchases": 3, "lastPrice": 1.15, "minPrice": 1.05}]
        def fake_search(query, _channel):
            return [product("Dallmayr Prodomo 500g", price=699, regular=999)] if query.startswith("Dallmayr") else []
        result = check_items(items, {"REWE Bio Joghurt 500g": "456"}, fake_search)
        self.assertEqual([row["status"] for row in result["items"]], ["offer", "unavailable"])
        self.assertEqual(result["items"][0]["price"], 6.99)
        self.assertEqual(result["items"][0]["regular"], 9.99)

    def test_no_hit_without_prior_match_is_not_called_unavailable(self):
        result = check_items([{"name": "Unbekannter Artikel", "purchases": 2}], search_fn=lambda _query, _channel: [])
        self.assertEqual(result["items"][0]["status"], "unmapped")

    def test_delivery_search_uses_online_channel(self):
        seen = []
        def fake_search(query, channel):
            seen.append((query, channel))
            return [product("Kerrygold Butter 250g", price=299, regular=349)]
        result = check_items([{"name": "Kerrygold Butter 250g", "purchases": 3}],
                             search_fn=fake_search, channel="online")
        self.assertEqual(seen, [("Kerrygold Butter 250g", "online")])
        self.assertEqual(result["channel"], "online")
        self.assertEqual(result["items"][0]["status"], "offer")

    def test_rate_limit_stops_the_batch(self):
        with patch("rewe_shop.urlopen", side_effect=HTTPError("https://www.rewe.de", 429, "limit", {}, None)) as request, \
                patch("rewe_shop.time.sleep"), patch("rewe_shop._pace_request"):
            with self.assertRaises(ShopThrottled):
                search("Beispiel", "online")
        self.assertEqual(request.call_count, 3)

    def test_rate_limit_keeps_completed_rows_for_resume(self):
        items = [{"name": "Kerrygold Butter 250g", "purchases": 3},
                 {"name": "REWE Bio Joghurt 500g", "purchases": 2}]
        def fake_search(query, _channel):
            if query.startswith("REWE"):
                raise ShopThrottled(429)
            return [product("Kerrygold Butter 250g", price=299, regular=349)]
        result = check_items(items, search_fn=fake_search, channel="online")
        self.assertTrue(result["paused"])
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["status"], "offer")

    def test_one_denied_item_does_not_stop_the_next(self):
        items = [{"name": "Gesperrter Artikel", "purchases": 1},
                 {"name": "Kerrygold Butter 250g", "purchases": 3}]
        def fake_search(query, _channel):
            if query.startswith("Gesperrter"):
                raise ShopThrottled(403)
            return [product("Kerrygold Butter 250g")]
        result = check_items(items, search_fn=fake_search)
        self.assertFalse(result["paused"])
        self.assertEqual([row["status"] for row in result["items"]], ["error", "available"])

    def test_offer_pages_use_market_filter_without_purchase_names(self):
        requests = []
        def fake_page(parameters, channel):
            requests.append((parameters, channel))
            page = parameters["page"]
            return {"pagination": {"page": page, "totalPages": 2},
                    "search": {"selectedFacets": {"attribute": ["discounted"]}},
                    "_embedded": {"products": [product("Kerrygold Butter 250g", product_id=str(page),
                                                       price=299, regular=349)]}}
        with patch("rewe_shop._catalogue_page", side_effect=fake_page):
            offers = discounted_products("online")
        self.assertEqual(len(offers), 2)
        self.assertEqual(requests, [
            ({"attribute": "discounted", "page": 1}, "online"),
            ({"attribute": "discounted", "page": 2}, "online")])

    def test_all_purchased_items_are_separated_by_channel_and_market(self):
        connection = sqlite3.connect(":memory:")
        connection.executescript("""
            CREATE TABLE receipts(id INTEGER, date TEXT, receipt_type TEXT, market_id TEXT);
            CREATE TABLE items(id INTEGER, receipt_id INTEGER, name TEXT, unit_price REAL);
            INSERT INTO receipts VALUES (1,'2026-09-20','ebon','5775'),
                (2,'2026-09-21','ebon','5775'),(3,'2026-09-22','shop',NULL),
                (4,'2026-09-23','shop',NULL),(5,'2026-09-24','ebon','5685');
            INSERT INTO items VALUES (1,1,'Kaffee 500g',6.99),(2,2,'Kaffee 500g',5.99),
                (3,1,'PFAND 0,25',0.25),(4,2,'PFAND 0,25',0.25),
                (5,3,'Kaffee 500g',9.99),(6,4,'Kaffee 500g',8.99),
                (7,2,'Brot',2.49),(8,5,'Brot',3.19);
        """)
        self.assertEqual(purchased_items(connection, "ebon", "5775"), [
            {"name": "Kaffee 500g", "purchases": 2, "lastPrice": 5.99, "minPrice": 5.99},
            {"name": "Brot", "purchases": 1, "lastPrice": 2.49, "minPrice": 2.49}])
        self.assertEqual(purchased_items(connection, "shop"), [
            {"name": "Kaffee 500g", "purchases": 2, "lastPrice": 8.99, "minPrice": 8.99}])


if __name__ == "__main__":
    unittest.main()
