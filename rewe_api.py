#!/usr/bin/env python3
"""Local, read-only HTTP API for the REWE eBon database.

This process deliberately has no import, mail, upload, migration, or write code.
It always binds to the IPv4 loopback address and opens SQLite with mode=ro.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import sys
import time
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Any, Callable, TypeVar
from urllib.parse import quote, urlsplit


HOST = "127.0.0.1"
DEFAULT_PORT = 7332
DEFAULT_DB_PATH = Path("/Users/marc/Library/Application Support/Rewe/rewe_ebons.db")
DEFAULT_PDF_DIR = Path("/Users/marc/Library/Application Support/Rewe/pdfs")
DEFAULT_ALLOWED_ORIGINS = (
    "http://127.0.0.1:4173",
    "http://localhost:4173",
    "http://127.0.0.1:3000",
    "http://localhost:3000",
)
DB_RETRY_DELAYS = (0.0, 0.075, 0.25, 0.5)
BUSY_TIMEOUT_MS = 3_000

_RECEIPT_PATH = re.compile(r"^/api/v1/rewe/receipts/([1-9][0-9]*)$")
_PDF_PATH = re.compile(r"^/api/v1/rewe/receipts/([1-9][0-9]*)/pdf$")
_T = TypeVar("_T")


class DatabaseUnavailable(RuntimeError):
    """The database cannot currently be read safely."""


class ReceiptNotFound(LookupError):
    """A requested receipt does not exist."""


def _utc_iso(timestamp: float | None = None) -> str:
    value = datetime.now(timezone.utc) if timestamp is None else datetime.fromtimestamp(timestamp, timezone.utc)
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _money(value: Any) -> float:
    return round(float(value or 0), 2)


def database_modified_at(database_path: Path) -> str | None:
    """Return the newest mtime of SQLite's main file and its WAL, if present."""

    timestamps: list[float] = []
    for candidate in (database_path, Path(f"{database_path}-wal")):
        try:
            timestamps.append(candidate.stat().st_mtime)
        except OSError:
            continue
    return _utc_iso(max(timestamps)) if timestamps else None


def open_readonly_connection(database_path: Path) -> sqlite3.Connection:
    """Open SQLite in URI read-only mode and additionally prohibit writes."""

    encoded_path = quote(str(database_path.resolve()), safe="/")
    connection = sqlite3.connect(
        f"file:{encoded_path}?mode=ro",
        uri=True,
        timeout=BUSY_TIMEOUT_MS / 1_000,
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    return connection


class PdfIndex:
    """A flat, traversal-safe view of the configured receipt PDF directory."""

    def __init__(self, directory: Path):
        self.directory = directory
        try:
            self.root = directory.resolve(strict=True)
            candidates = sorted(directory.iterdir(), key=lambda item: item.name.casefold())
        except OSError:
            self.root = None
            candidates = []

        self.files: list[Path] = []
        self.by_stem: dict[str, Path] = {}
        for candidate in candidates:
            if candidate.suffix.casefold() != ".pdf" or not candidate.is_file():
                continue
            safe_candidate = self._contained_file(candidate)
            if safe_candidate is None:
                continue
            self.files.append(safe_candidate)
            self.by_stem.setdefault(candidate.stem, safe_candidate)

    def _contained_file(self, candidate: Path) -> Path | None:
        if self.root is None:
            return None
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            return None
        if resolved.parent != self.root or not resolved.is_file():
            return None
        return resolved

    def find(self, source: str | None, receipt_date: str | None) -> Path | None:
        # The database value is never appended to a directory. It is reduced to a
        # stem and used only as a lookup key into files we already enumerated.
        source_name = PurePosixPath((source or "").replace("\\", "/")).name
        source_stem = Path(source_name).stem
        if source_stem and source_stem in self.by_stem:
            return self.by_stem[source_stem]

        # Historical eBons sometimes have a human-readable PDF filename. This is
        # the same date fallback used by the former static JSON preparation.
        if receipt_date and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", receipt_date):
            year, month, day = receipt_date.split("-")
            date_needle = f"{day}.{month}.{year}"
            for candidate in self.files:
                if date_needle in candidate.name:
                    return candidate
        return None


class ReweRepository:
    """Read-only queries and response shaping for the API."""

    def __init__(self, database_path: Path, pdf_directory: Path, year: int | None = None):
        self.database_path = database_path
        self.pdf_directory = pdf_directory
        self.year = year or datetime.now().year

    def _read(self, operation: Callable[[sqlite3.Connection], _T]) -> _T:
        for attempt, delay in enumerate(DB_RETRY_DELAYS):
            if delay:
                time.sleep(delay)
            try:
                with closing(open_readonly_connection(self.database_path)) as connection:
                    connection.execute("BEGIN")
                    try:
                        result = operation(connection)
                    finally:
                        connection.rollback()
                    return result
            except sqlite3.Error as error:
                message = str(error).casefold()
                retryable = "locked" in message or "busy" in message
                if retryable and attempt + 1 < len(DB_RETRY_DELAYS):
                    continue
                raise DatabaseUnavailable from None
        raise DatabaseUnavailable

    @property
    def period(self) -> tuple[str, str]:
        return f"{self.year:04d}-01-01", f"{self.year + 1:04d}-01-01"

    @staticmethod
    def _item(row: sqlite3.Row) -> dict[str, Any]:
        quantity = row["quantity"] if row["quantity"] is not None else 1
        return {
            "id": row["id"],
            "name": row["name"],
            "price": _money(row["price"]),
            "unitPrice": None if row["unit_price"] is None else _money(row["unit_price"]),
            "quantity": quantity,
            "tax": row["tax"],
            "category": row["category"] or "Sonstiges",
        }

    @staticmethod
    def _receipt(row: sqlite3.Row, items: list[dict[str, Any]], pdf_path: Path | None) -> dict[str, Any]:
        receipt_id = row["id"]
        return {
            "id": receipt_id,
            "date": row["date"],
            "time": row["time"],
            "marketId": row["market_id"],
            "bonNumber": row["bon_nr"],
            "total": _money(row["total"]),
            "receiptType": row["receipt_type"] or "ebon",
            "pdfUrl": f"/api/v1/rewe/receipts/{receipt_id}/pdf" if pdf_path else None,
            "items": items,
        }

    def status(self) -> dict[str, Any]:
        def query(connection: sqlite3.Connection) -> tuple[int, sqlite3.Row | None]:
            count = connection.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
            latest = connection.execute(
                """
                SELECT id, date
                FROM receipts
                ORDER BY date DESC, COALESCE(time, '') DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
            return count, latest

        count, latest = self._read(query)
        latest_value = {"id": latest["id"], "date": latest["date"]} if latest else None
        return {
            "status": "ok",
            "reachable": True,
            "databaseModifiedAt": database_modified_at(self.database_path),
            "receiptCount": count,
            "latestReceiptId": latest["id"] if latest else None,
            "latestReceiptDate": latest["date"] if latest else None,
            "latestReceipt": latest_value,
        }

    def all_data(self) -> dict[str, Any]:
        period_start, period_end = self.period

        def query(connection: sqlite3.Connection) -> tuple[list[sqlite3.Row], list[sqlite3.Row]]:
            receipts = connection.execute(
                """
                SELECT id, date, time, market_id, bon_nr, total, source, receipt_type
                FROM receipts
                WHERE date >= ? AND date < ?
                ORDER BY date DESC, COALESCE(time, '') DESC, id DESC
                """,
                (period_start, period_end),
            ).fetchall()
            items = connection.execute(
                """
                SELECT i.id, i.receipt_id, i.name, i.price, i.unit_price,
                       i.quantity, i.tax, COALESCE(i.category, 'Sonstiges') AS category
                FROM items AS i
                JOIN receipts AS r ON r.id = i.receipt_id
                WHERE r.date >= ? AND r.date < ?
                ORDER BY r.date DESC, COALESCE(r.time, '') DESC, i.id
                """,
                (period_start, period_end),
            ).fetchall()
            return receipts, items

        receipt_rows, item_rows = self._read(query)
        pdf_index = PdfIndex(self.pdf_directory)
        items_by_receipt: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in item_rows:
            items_by_receipt[row["receipt_id"]].append(self._item(row))

        receipts: list[dict[str, Any]] = []
        monthly: dict[str, dict[str, Any]] = {}
        categories: dict[str, float] = defaultdict(float)
        products: dict[str, dict[str, Any]] = {}
        pdf_count = 0

        for row in receipt_rows:
            pdf_path = pdf_index.find(row["source"], row["date"])
            if pdf_path:
                pdf_count += 1
            receipt = self._receipt(row, items_by_receipt[row["id"]], pdf_path)
            receipts.append(receipt)

            month = row["date"][:7]
            month_value = monthly.setdefault(month, {"month": month, "total": 0.0, "receipts": 0})
            month_value["total"] += receipt["total"]
            month_value["receipts"] += 1

            for item in receipt["items"]:
                categories[item["category"]] += item["price"]
                product = products.setdefault(
                    item["name"],
                    {"name": item["name"], "total": 0.0, "quantity": 0, "purchases": 0},
                )
                product["total"] += item["price"]
                product["quantity"] += item["quantity"]
                product["purchases"] += 1

        total = _money(sum(receipt["total"] for receipt in receipts))
        generated_at = _utc_iso()
        receipt_count = len(receipts)
        item_count = len(item_rows)
        monthly_values = sorted(monthly.values(), key=lambda row: row["month"])
        for row in monthly_values:
            row["total"] = _money(row["total"])
        category_values = sorted(
            ({"name": name, "value": _money(value)} for name, value in categories.items()),
            key=lambda row: row["value"],
            reverse=True,
        )
        product_values = sorted(products.values(), key=lambda row: row["total"], reverse=True)[:30]
        for row in product_values:
            row["total"] = _money(row["total"])

        latest_date = receipts[0]["date"] if receipts else None
        earliest_date = receipts[-1]["date"] if receipts else None
        return {
            "meta": {
                "generatedAt": generated_at,
                "databaseModifiedAt": database_modified_at(self.database_path),
                "latestReceiptDate": latest_date,
                "source": "Lokale REWE-eBon-Datenbank",
                "receiptCount": receipt_count,
                "itemCount": item_count,
                # Compatibility with the former rewe-data.json consumer.
                "preparedAt": generated_at,
                "periodStart": earliest_date,
                "periodEnd": latest_date,
                "pdfCount": pdf_count,
            },
            "metrics": {
                "receiptCount": receipt_count,
                "itemCount": item_count,
                "total": total,
                "averageBasket": _money(total / receipt_count) if receipt_count else 0,
            },
            "monthly": monthly_values,
            "categories": category_values,
            "topItems": product_values,
            "receipts": receipts,
        }

    def receipt(self, receipt_id: int) -> dict[str, Any]:
        def query(connection: sqlite3.Connection) -> tuple[sqlite3.Row | None, list[sqlite3.Row]]:
            receipt_row = connection.execute(
                """
                SELECT id, date, time, market_id, bon_nr, total, source, receipt_type
                FROM receipts
                WHERE id = ?
                """,
                (receipt_id,),
            ).fetchone()
            if receipt_row is None:
                return None, []
            item_rows = connection.execute(
                """
                SELECT id, receipt_id, name, price, unit_price, quantity, tax,
                       COALESCE(category, 'Sonstiges') AS category
                FROM items
                WHERE receipt_id = ?
                ORDER BY id
                """,
                (receipt_id,),
            ).fetchall()
            return receipt_row, item_rows

        receipt_row, item_rows = self._read(query)
        if receipt_row is None:
            raise ReceiptNotFound
        pdf_path = PdfIndex(self.pdf_directory).find(receipt_row["source"], receipt_row["date"])
        return self._receipt(receipt_row, [self._item(row) for row in item_rows], pdf_path)

    def receipt_pdf(self, receipt_id: int) -> Path:
        def query(connection: sqlite3.Connection) -> sqlite3.Row | None:
            return connection.execute(
                "SELECT source, date FROM receipts WHERE id = ?",
                (receipt_id,),
            ).fetchone()

        receipt_row = self._read(query)
        if receipt_row is None:
            raise ReceiptNotFound
        pdf_path = PdfIndex(self.pdf_directory).find(receipt_row["source"], receipt_row["date"])
        if pdf_path is None:
            raise ReceiptNotFound
        return pdf_path


class ReweApiServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request: Any, client_address: Any) -> None:
        # Browsers routinely cancel in-flight fetches during reload/navigation.
        # socketserver would otherwise print a full traceback even though the API
        # and database are healthy. Keep reporting every unexpected server error.
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        repository: ReweRepository,
        allowed_origins: frozenset[str],
    ):
        self.repository = repository
        self.allowed_origins = allowed_origins
        super().__init__(server_address, handler_class)


class ReweApiHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "ReweLocalAPI/1.0"
    sys_version = ""

    @property
    def api_server(self) -> ReweApiServer:
        return self.server  # type: ignore[return-value]

    def log_message(self, _format: str, *args: Any) -> None:
        # Avoid logging request details or internal paths. Startup and fatal errors
        # are reported by main(), while routine requests remain quiet.
        return

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        return origin is None or origin in self.api_server.allowed_origins

    def _common_headers(self, content_type: str, content_length: int) -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(content_length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        origin = self.headers.get("Origin")
        if origin and origin in self.api_server.allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self._common_headers("application/json; charset=utf-8", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: HTTPStatus, code: str, message: str) -> None:
        self._send_json(status, {"error": {"code": code, "message": message}})

    @staticmethod
    def _known_path(path: str) -> bool:
        return (
            path in {"/api/v1/rewe", "/api/v1/rewe/status"}
            or _RECEIPT_PATH.fullmatch(path) is not None
            or _PDF_PATH.fullmatch(path) is not None
        )

    def do_OPTIONS(self) -> None:
        path = urlsplit(self.path).path
        if not self._origin_allowed():
            self._send_error_json(HTTPStatus.FORBIDDEN, "origin_not_allowed", "Origin nicht erlaubt.")
            return
        if not self._known_path(path):
            self._send_error_json(HTTPStatus.NOT_FOUND, "not_found", "Endpunkt nicht gefunden.")
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Accept, Content-Type")
        origin = self.headers.get("Origin")
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()

    def do_GET(self) -> None:
        if not self._origin_allowed():
            self._send_error_json(HTTPStatus.FORBIDDEN, "origin_not_allowed", "Origin nicht erlaubt.")
            return

        path = urlsplit(self.path).path
        try:
            if path == "/api/v1/rewe/status":
                self._send_json(HTTPStatus.OK, self.api_server.repository.status())
                return
            if path == "/api/v1/rewe":
                self._send_json(HTTPStatus.OK, self.api_server.repository.all_data())
                return

            pdf_match = _PDF_PATH.fullmatch(path)
            if pdf_match:
                receipt_id = int(pdf_match.group(1))
                self._send_pdf(receipt_id, self.api_server.repository.receipt_pdf(receipt_id))
                return

            receipt_match = _RECEIPT_PATH.fullmatch(path)
            if receipt_match:
                receipt_id = int(receipt_match.group(1))
                self._send_json(HTTPStatus.OK, self.api_server.repository.receipt(receipt_id))
                return

            self._send_error_json(HTTPStatus.NOT_FOUND, "not_found", "Endpunkt nicht gefunden.")
        except ReceiptNotFound:
            self._send_error_json(HTTPStatus.NOT_FOUND, "receipt_not_found", "Bon oder PDF nicht gefunden.")
        except DatabaseUnavailable:
            self._send_error_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "database_unavailable",
                "Die REWE-Datenbank ist vorübergehend nicht verfügbar.",
            )
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", "Interner API-Fehler.")

    def _send_pdf(self, receipt_id: int, pdf_path: Path) -> None:
        try:
            size = pdf_path.stat().st_size
            source = pdf_path.open("rb")
        except OSError:
            raise ReceiptNotFound from None
        with source:
            self.send_response(HTTPStatus.OK)
            self._common_headers("application/pdf", size)
            self.send_header("Content-Disposition", f'inline; filename="rewe-receipt-{receipt_id}.pdf"')
            self.end_headers()
            shutil.copyfileobj(source, self.wfile)

    def _method_not_allowed(self) -> None:
        if not self._origin_allowed():
            self._send_error_json(HTTPStatus.FORBIDDEN, "origin_not_allowed", "Origin nicht erlaubt.")
            return
        self._send_error_json(HTTPStatus.METHOD_NOT_ALLOWED, "method_not_allowed", "Nur GET ist erlaubt.")

    do_POST = _method_not_allowed
    do_PUT = _method_not_allowed
    do_PATCH = _method_not_allowed
    do_DELETE = _method_not_allowed


def _validate_origin(origin: str) -> str:
    if origin == "*":
        raise ValueError("Wildcard-Origin ist nicht erlaubt")
    parsed = urlsplit(origin)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Nur explizite lokale Origins sind erlaubt")
    return origin.rstrip("/")


def allowed_origins_from_environment() -> frozenset[str]:
    raw = os.environ.get("REWE_API_ALLOWED_ORIGINS")
    values = DEFAULT_ALLOWED_ORIGINS if raw is None else tuple(part.strip() for part in raw.split(",") if part.strip())
    return frozenset(_validate_origin(value) for value in values)


def port_from_environment() -> int:
    raw = os.environ.get("REWE_API_PORT", str(DEFAULT_PORT))
    try:
        port = int(raw)
    except ValueError:
        raise ValueError("REWE_API_PORT muss eine Zahl sein") from None
    if not 1 <= port <= 65_535:
        raise ValueError("REWE_API_PORT muss zwischen 1 und 65535 liegen")
    return port


def create_server(
    *,
    port: int,
    database_path: Path = DEFAULT_DB_PATH,
    pdf_directory: Path = DEFAULT_PDF_DIR,
    allowed_origins: frozenset[str] | None = None,
    year: int | None = None,
) -> ReweApiServer:
    if not 0 <= port <= 65_535:
        raise ValueError("Ungültiger Port")
    repository = ReweRepository(database_path, pdf_directory, year=year)
    return ReweApiServer(
        (HOST, port),
        ReweApiHandler,
        repository,
        allowed_origins if allowed_origins is not None else frozenset(DEFAULT_ALLOWED_ORIGINS),
    )


def main() -> int:
    try:
        port = port_from_environment()
        origins = allowed_origins_from_environment()
        server = create_server(port=port, allowed_origins=origins)
    except (OSError, ValueError) as error:
        print(f"REWE-API konnte nicht gestartet werden: {error}", file=sys.stderr)
        return 2

    print(f"REWE-API: http://{HOST}:{port}/api/v1/rewe/status")
    print("Nur lokal, SQLite read-only. Beenden mit Ctrl-C.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
