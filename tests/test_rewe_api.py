import hashlib
import http.client
import json
import sqlite3
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


from rewe_api import DEFAULT_ALLOWED_ORIGINS, create_server, open_readonly_connection


ALLOWED_ORIGIN = "http://127.0.0.1:4173"


class ReweApiTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.database_path = self.root / "rewe.db"
        self.pdf_directory = self.root / "pdfs"
        self.pdf_directory.mkdir()
        self.year = datetime.now().year
        self.older_date = f"{self.year:04d}-01-04"
        self.latest_date = f"{self.year:04d}-09-18"

        connection = sqlite3.connect(self.database_path)
        connection.executescript(
            """
            CREATE TABLE receipts (
                id INTEGER PRIMARY KEY,
                date TEXT NOT NULL,
                time TEXT,
                market_id TEXT,
                bon_nr TEXT,
                total REAL,
                source TEXT,
                receipt_type TEXT DEFAULT 'ebon'
            );
            CREATE TABLE items (
                id INTEGER PRIMARY KEY,
                receipt_id INTEGER REFERENCES receipts(id),
                name TEXT NOT NULL,
                price REAL NOT NULL,
                unit_price REAL,
                quantity INTEGER DEFAULT 1,
                tax TEXT,
                category TEXT
            );
            """
        )
        connection.executemany(
            """
            INSERT INTO receipts (id, date, time, market_id, bon_nr, total, source, receipt_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (1, self.older_date, "08:15", "1000", "A-1", 5.0, "older.eml", "ebon"),
                (2, self.latest_date, "10:58", "5685", "9206", 12.5, "latest.eml", "ebon"),
            ),
        )
        connection.executemany(
            """
            INSERT INTO items (id, receipt_id, name, price, unit_price, quantity, tax, category)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (1, 1, "Apfel", 2.0, 2.0, 1, "A", "Obst"),
                (2, 1, "Brot", 3.0, 3.0, 1, "B", "Backwaren"),
                (3, 2, "Kaffee", 12.5, 6.25, 2, "B", "Getränke"),
            ),
        )
        connection.commit()
        connection.close()

        self.pdf_bytes = b"%PDF-1.4\n% local test receipt\n%%EOF\n"
        (self.pdf_directory / "latest.pdf").write_bytes(self.pdf_bytes)

        self.server = create_server(
            port=0,
            database_path=self.database_path,
            pdf_directory=self.pdf_directory,
            allowed_origins=frozenset({ALLOWED_ORIGIN}),
            year=self.year,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary_directory.cleanup()

    def request(self, path, *, method="GET", origin=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Origin": origin} if origin is not None else {}
        connection.request(method, path, headers=headers)
        response = connection.getresponse()
        body = response.read()
        status = response.status
        response_headers = dict(response.getheaders())
        connection.close()
        return status, response_headers, body

    def json_request(self, path, *, method="GET", origin=None):
        status, headers, body = self.request(path, method=method, origin=origin)
        return status, headers, json.loads(body)

    def test_status_reports_database_and_latest_receipt(self):
        status, headers, payload = self.json_request("/api/v1/rewe/status")

        self.assertEqual(status, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["reachable"])
        self.assertEqual(payload["receiptCount"], 2)
        self.assertEqual(payload["latestReceipt"], {"id": 2, "date": self.latest_date})
        self.assertIsNotNone(payload["databaseModifiedAt"])
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_server_binds_only_to_ipv4_loopback(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_default_origins_cover_both_local_dashboard_ports(self):
        self.assertEqual(
            set(DEFAULT_ALLOWED_ORIGINS),
            {
                "http://127.0.0.1:4173",
                "http://localhost:4173",
                "http://127.0.0.1:3000",
                "http://localhost:3000",
            },
        )

    def test_main_endpoint_matches_sqlite_totals_and_item_count(self):
        with sqlite3.connect(self.database_path) as connection:
            expected_total, expected_receipts = connection.execute(
                "SELECT ROUND(SUM(total), 2), COUNT(*) FROM receipts"
            ).fetchone()
            expected_items = connection.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        before = hashlib.sha256(self.database_path.read_bytes()).digest()

        status, headers, payload = self.json_request("/api/v1/rewe")

        self.assertEqual(status, 200)
        self.assertEqual(payload["metrics"]["total"], expected_total)
        self.assertEqual(payload["metrics"]["receiptCount"], expected_receipts)
        self.assertEqual(payload["metrics"]["itemCount"], expected_items)
        self.assertEqual(payload["meta"]["latestReceiptDate"], self.latest_date)
        self.assertEqual(payload["meta"]["source"], "Lokale REWE-eBon-Datenbank")
        self.assertEqual(payload["receipts"][0]["id"], 2)
        self.assertEqual(len(payload["receipts"][0]["items"]), 1)
        self.assertEqual(payload["receipts"][0]["pdfUrl"], "/api/v1/rewe/receipts/2/pdf")
        self.assertNotIn("source", payload["receipts"][0])
        self.assertNotIn(str(self.root), json.dumps(payload))
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(hashlib.sha256(self.database_path.read_bytes()).digest(), before)

    def test_single_receipt_contains_its_items(self):
        status, _headers, payload = self.json_request("/api/v1/rewe/receipts/2")

        self.assertEqual(status, 200)
        self.assertEqual(payload["id"], 2)
        self.assertEqual(payload["bonNumber"], "9206")
        self.assertEqual(payload["items"][0]["name"], "Kaffee")

    def test_existing_pdf_is_delivered_without_exposing_its_filename(self):
        status, headers, body = self.request("/api/v1/rewe/receipts/2/pdf")

        self.assertEqual(status, 200)
        self.assertEqual(body, self.pdf_bytes)
        self.assertEqual(headers["Content-Type"], "application/pdf")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["Content-Disposition"], 'inline; filename="rewe-receipt-2.pdf"')

    def test_unknown_receipt_returns_404(self):
        status, _headers, payload = self.json_request("/api/v1/rewe/receipts/999999")

        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "receipt_not_found")
        self.assertNotIn(str(self.root), json.dumps(payload))

    def test_shop_check_requires_explicit_local_origin_and_json(self):
        def post(origin=None, content_type="application/json", body=b'{"known":{}}'):
            connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
            headers = {"Content-Type": content_type}
            if origin is not None:
                headers["Origin"] = origin
            connection.request("POST", "/api/v1/rewe/shop-check", body=body, headers=headers)
            response = connection.getresponse()
            status, body = response.status, response.read()
            connection.close()
            return status, json.loads(body)

        self.assertEqual(post()[0], 403)
        self.assertEqual(post("https://other.example")[0], 403)
        self.assertEqual(post(ALLOWED_ORIGIN, "text/plain")[0], 415)
        with patch.object(self.server.repository, "shop_check", return_value={"items": []}) as check:
            status, payload = post(ALLOWED_ORIGIN)
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"items": []})
        check.assert_called_once_with("market", {}, 0, 25)
        with patch.object(self.server.repository, "shop_check", return_value={"items": []}) as check:
            self.assertEqual(post(ALLOWED_ORIGIN, body=b'{"channel":"online","known":{}}')[0], 200)
        check.assert_called_once_with("online", {}, 0, 25)
        self.assertEqual(post(ALLOWED_ORIGIN, body=b'{"channel":"unknown"}')[0], 400)
        self.assertEqual(post(ALLOWED_ORIGIN, body=b'{"offset":-1}')[0], 400)
        self.assertEqual(post(ALLOWED_ORIGIN, body=b'{"limit":26}')[0], 400)

    def test_shop_items_list_is_read_only_and_channel_specific(self):
        with patch.object(self.server.repository, "shop_items", return_value={"channel":"online","total":0,"items":[]}) as listing:
            status, _headers, payload = self.json_request("/api/v1/rewe/shop-items?channel=online")
        self.assertEqual(status, 200)
        self.assertEqual(payload["channel"], "online")
        listing.assert_called_once_with("online")
        self.assertEqual(self.json_request("/api/v1/rewe/shop-items?channel=wrong")[0], 400)

    def test_shop_check_returns_one_page_with_progress(self):
        items = [{"name": f"Artikel {n}", "purchases": 1} for n in range(54)]
        with patch.object(self.server.repository, "_read", return_value=items), \
                patch("rewe_api.rewe_shop.check_items", side_effect=lambda batch, known, channel: {"channel":channel,"items":batch}):
            middle = self.server.repository.shop_check("market", {}, 25, 25)
            last = self.server.repository.shop_check("market", {}, 50, 25)
        self.assertEqual([row["name"] for row in middle["items"]], [f"Artikel {n}" for n in range(25, 50)])
        self.assertEqual((middle["total"], middle["nextOffset"]), (54, 50))
        self.assertEqual((len(last["items"]), last["nextOffset"]), (4, None))

    def test_shop_check_resumes_after_partial_rate_limited_page(self):
        items = [{"name": f"Artikel {n}", "purchases": 1} for n in range(3)]
        with patch.object(self.server.repository, "_read", return_value=items), \
                patch("rewe_api.rewe_shop.check_items", return_value={
                    "channel": "market", "items": [items[0]], "paused": True}):
            page = self.server.repository.shop_check("market", {}, 0, 3)
        self.assertEqual(page["nextOffset"], 1)
        self.assertTrue(page["paused"])
        self.assertEqual(page["items"], [items[0]])

    def test_path_traversal_is_not_a_route(self):
        status, _headers, payload = self.json_request(
            "/api/v1/rewe/receipts/2/pdf/%2e%2e/%2e%2e/etc/passwd"
        )

        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "not_found")

    def test_database_connection_rejects_writes(self):
        before = hashlib.sha256(self.database_path.read_bytes()).digest()
        connection = open_readonly_connection(self.database_path)
        try:
            self.assertEqual(connection.execute("PRAGMA query_only").fetchone()[0], 1)
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("INSERT INTO receipts (date) VALUES (?)", (self.latest_date,))
        finally:
            connection.close()
        self.assertEqual(hashlib.sha256(self.database_path.read_bytes()).digest(), before)

    def test_new_receipt_appears_without_server_restart(self):
        status, _headers, before = self.json_request("/api/v1/rewe")
        self.assertEqual(status, 200)
        self.assertNotIn(3, [receipt["id"] for receipt in before["receipts"]])

        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO receipts (id, date, time, market_id, bon_nr, total, source, receipt_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (3, f"{self.year:04d}-09-19", "09:00", "7777", "NEW", 4.25, "new.eml", "ebon"),
            )
            connection.execute(
                """
                INSERT INTO items (id, receipt_id, name, price, unit_price, quantity, tax, category)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (4, 3, "Neu", 4.25, 4.25, 1, "B", "Sonstiges"),
            )
            connection.commit()

        status, _headers, after = self.json_request("/api/v1/rewe")
        self.assertEqual(status, 200)
        self.assertEqual(after["receipts"][0]["id"], 3)
        self.assertEqual(after["metrics"]["receiptCount"], 3)
        self.assertEqual(after["metrics"]["itemCount"], 4)

    def test_disallowed_cors_origin_is_rejected(self):
        status, headers, payload = self.json_request(
            "/api/v1/rewe/status", origin="https://example.invalid"
        )

        self.assertEqual(status, 403)
        self.assertEqual(payload["error"]["code"], "origin_not_allowed")
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_allowed_cors_origin_is_echoed_without_wildcard(self):
        status, headers, _payload = self.json_request(
            "/api/v1/rewe/status", origin=ALLOWED_ORIGIN
        )

        self.assertEqual(status, 200)
        self.assertEqual(headers["Access-Control-Allow-Origin"], ALLOWED_ORIGIN)
        self.assertNotEqual(headers["Access-Control-Allow-Origin"], "*")

    def test_write_methods_are_not_available(self):
        status, _headers, payload = self.json_request("/api/v1/rewe", method="POST")

        self.assertEqual(status, 405)
        self.assertEqual(payload["error"]["code"], "method_not_allowed")


if __name__ == "__main__":
    unittest.main()
