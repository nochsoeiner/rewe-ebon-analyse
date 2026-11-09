"""User-triggered comparison of purchased items with two REWE catalogues.

The pickup catalogue is a useful signal for this market, but it is not a live
inventory of the shelves. No network request is made at import time.
"""

from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def load_offer_snapshot(path) -> dict | None:
    """Keep the last complete catalogue; expiry is evaluated per offer in the UI."""
    try:
        snapshot = json.loads(path.read_text("utf-8"))
        if not isinstance(snapshot, dict):
            return None
        checked_at = datetime.fromisoformat(snapshot["checkedAt"])
        if checked_at.tzinfo is None:
            return None
        for channel in ("market", "online"):
            data = snapshot["channels"][channel]
            if (not isinstance(data["items"], list)
                    or any(not isinstance(row, dict) or not isinstance(row.get("name"), str)
                           for row in data["items"])
                    or type(data["catalogueOffers"]) is not int
                    or data["catalogueOffers"] < 0):
                return None
        return snapshot
    except (OSError, ValueError, KeyError, TypeError):
        return None


CHANNELS = {
    "market": {
        "marketId": "4040430",
        "serviceType": "PICKUP",
        "receiptType": "ebon",
        "receiptMarketId": "5775",
        "label": "REWE Markt Holzhäuserstr. 110 · Leipzig / Stötteritz",
        "url": "https://www.rewe.de/angebote/leipzig-stoetteritz/4040430/rewe-markt-holzhaeuserstr-110/",
    },
    "online": {
        "marketId": "4600006",
        "serviceType": "DELIVERY",
        "receiptType": "shop",
        "receiptMarketId": None,
        "label": "REWE Lieferservice · PLZ 04299",
        "url": "https://www.rewe.de/shop/angebote/",
    },
}
SEARCH_URL = "https://www.rewe.de/shop/api/products"
_EXCLUDE = re.compile(r"^(?:pfand|leergut|bon|gutschein|rabatt|summe|tüte|tuete)\b", re.I)


class ShopThrottled(RuntimeError):
    """REWE has stopped accepting catalogue lookups for now."""

    def __init__(self, code: int):
        self.code = code
        super().__init__(f"REWE HTTP {code}")


_request_lock = threading.Lock()
_next_request_at = 0.0
# Interactive defaults. The unattended night job slows down via configure_pacing().
_REQUEST_INTERVAL = 0.8
_RETRY_DELAYS = (5, 15)
_MAX_RETRY_AFTER = 30
MAX_OFFER_PAGES = 200


def configure_pacing(interval: float, retry_delays: tuple[int, int], max_retry_after: int) -> None:
    """Use longer gaps for background runs, where finishing later is acceptable."""
    global _REQUEST_INTERVAL, _RETRY_DELAYS, _MAX_RETRY_AFTER
    _REQUEST_INTERVAL, _RETRY_DELAYS, _MAX_RETRY_AFTER = interval, retry_delays, max_retry_after


def _pace_request() -> None:
    """Space lookups across batches and concurrent local clients."""
    global _next_request_at
    with _request_lock:
        now = time.monotonic()
        if now < _next_request_at:
            time.sleep(_next_request_at - now)
        _next_request_at = time.monotonic() + _REQUEST_INTERVAL


_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
_UNIT = r"(?:kg|g|mg|l|ml|cl|stk|st)"


def normalize(value: str) -> str:
    # eBons spell umlauts as AE/OE/UE ("MUELLER"), the shop uses "Müller".
    value = value.casefold().translate(_UMLAUTS)
    value = "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))
    # "1,0L", "1.0 l" and "1l" describe the same package size.
    value = re.sub(rf"(\d)[,.]0+\s*(?={_UNIT}\b)", r"\1", value)
    value = re.sub(rf"(\d)\s+(?={_UNIT}\b)", r"\1", value)
    return " ".join(re.findall(r"[a-z0-9]+", value))


def _score(needle: str, title: str) -> float:
    a, b = normalize(needle), normalize(title)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    wanted, found = set(a.split()), set(b.split())
    matching = {word for word in wanted if word in found or
                (len(word) >= 4 and any(candidate.startswith(word) for candidate in found))}
    if len(wanted) < 2 or len(matching) < 2:
        return 0.0
    # An abbreviated receipt name may omit the brand and package size. Keep
    # matching conservative when the shop has several similarly named variants.
    coverage = len(matching) / len(wanted)
    similarity = SequenceMatcher(None, a, b).ratio()
    return round(0.7 * coverage + 0.3 * similarity, 4)


def _exact_abbreviation(needle: str, title: str) -> bool:
    wanted, found = normalize(needle).split(), normalize(title).split()
    return len(wanted) >= 2 and len(wanted) == len(found) and all(
        a == b or (len(a) >= 4 and b.startswith(a)) for a, b in zip(wanted, found)
    )


def choose_product(name: str, products: list[dict], title_key: str = "productName") -> dict | None:
    ranked = sorted(((_score(name, p.get(title_key, "")), p) for p in products),
                    key=lambda pair: pair[0], reverse=True)
    if not ranked or ranked[0][0] < 0.84:
        return None
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 0.08:
        exact = [p for _, p in ranked if _exact_abbreviation(name, p.get(title_key, ""))]
        if len(exact) != 1 or exact[0] is not ranked[0][1]:
            return None
    return ranked[0][1]


def _product_data(product: dict) -> dict:
    articles = product.get("_embedded", {}).get("articles") or []
    priced = [a.get("_embedded", {}).get("listing", {}).get("pricing", {}) for a in articles]
    priced = [p for p in priced if isinstance(p.get("currentRetailPrice"), (int, float))]
    price = min(priced, key=lambda p: p["currentRetailPrice"]) if priced else None
    discount = price.get("discount") if price else None
    current = price["currentRetailPrice"] / 100 if price else None
    regular = discount.get("regularPrice") / 100 if isinstance(discount, dict) and discount.get("regularPrice") else None
    image = (((product.get("media") or {}).get("images") or [{}])[0].get("_links") or {}).get("self", {}).get("href")
    detail = (product.get("_links") or {}).get("detail", {}).get("href", "")
    return {
        "productId": str(product.get("id", "")),
        "title": product.get("productName", ""),
        "image": image if isinstance(image, str) and image.startswith("https://img.rewe-static.de/") else None,
        "shopUrl": "https://www.rewe.de/shop" + detail if isinstance(detail, str) and detail.startswith("/p/") else None,
        "price": current,
        "regular": regular,
        "discount": discount.get("discountRate") if isinstance(discount, dict) else None,
        "validUntil": discount.get("validTo") if isinstance(discount, dict) else None,
        "status": "offer" if regular is not None and current is not None and current < regular else
                  "available" if price is not None else "unavailable",
    }


def _catalogue_page(parameters: dict, channel: str) -> dict:
    config = CHANNELS[channel]
    url = SEARCH_URL + "?" + urlencode({**parameters, "market": config["marketId"],
                                        "serviceTypes": config["serviceType"]})
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
    for attempt in range(3):
        _pace_request()
        try:
            with urlopen(request, timeout=12) as response:
                data = response.read(2_000_001)
            break
        except HTTPError as error:
            if error.code == 403:
                raise ShopThrottled(403) from None
            if error.code != 429:
                raise
            if attempt == 2:
                raise ShopThrottled(429) from None
            retry_after = error.headers.get("Retry-After") if error.headers else None
            delay = (min(_MAX_RETRY_AFTER, max(1, int(retry_after)))
                     if retry_after and retry_after.isdecimal() else _RETRY_DELAYS[attempt])
            time.sleep(delay)
    if len(data) > 2_000_000:
        raise ValueError("REWE-Antwort zu groß")
    payload = json.loads(data)
    if (payload.get("search", {}).get("marketCode") != config["marketId"] or
            config["serviceType"] not in payload.get("search", {}).get("serviceTypes", [])):
        raise ValueError("REWE hat einen anderen Markt geliefert")
    if not isinstance(payload.get("_embedded", {}).get("products"), list):
        raise ValueError("REWE-Antwort enthält keine Produktliste")
    return payload


def search(query: str, channel: str = "market") -> list[dict]:
    return _catalogue_page({"search": query, "page": 1}, channel)["_embedded"]["products"]


def discounted_products(channel: str, progress: dict | None = None, on_page=None) -> list[dict]:
    """Read the shop's offer facet in pages, without sending purchase history.

    ``progress`` ({"page", "offers"}) resumes an interrupted run. ``on_page`` is
    called after every page so a throttled run can continue later where it
    stopped instead of starting over. The result holds ``_product_data`` rows.
    """
    progress = progress or {}
    offers = list(progress.get("offers") or [])
    page = progress.get("page") or 1
    total_pages = progress.get("totalPages") or page
    while page <= total_pages:
        payload = _catalogue_page({"attribute": "discounted", "page": page}, channel)
        pagination = payload.get("pagination", {})
        if (pagination.get("page") != page or
                not isinstance(pagination.get("totalPages"), int) or
                not 1 <= pagination["totalPages"] <= MAX_OFFER_PAGES or
                "discounted" not in payload.get("search", {}).get("selectedFacets", {}).get("attribute", [])):
            raise ValueError("REWE-Angebotsseiten sind unvollständig")
        total_pages = pagination["totalPages"]
        offers.extend(row for row in map(_product_data, payload["_embedded"]["products"])
                      if row["productId"] and row["status"] == "offer")
        page += 1
        if on_page is not None:
            on_page({"page": page, "totalPages": total_pages, "offers": offers})
    return list({row["productId"]: row for row in offers}.values())


def offer_snapshot(connection, catalogue: dict, product_map: dict | None = None) -> dict:
    """Match purchases locally against a complete offer catalogue.

    A product ID found earlier by a name search is the reliable link: the offer
    is then recognised regardless of how the eBon abbreviates the name. Names
    without an ID fall back to the conservative title comparison.
    """
    product_map = product_map or {}
    channels = {}
    for channel, config in CHANNELS.items():
        purchases = purchased_items(connection, config["receiptType"], config["receiptMarketId"])
        offers = catalogue["channels"][channel]
        by_id = {row["productId"]: row for row in offers}
        known = product_map.get(channel, {})
        rows = []
        for item in purchases:
            entry = known.get(item["name"]) or {}
            product_id = entry.get("productId")
            if product_id:
                offer = by_id.get(product_id)
                rows.append({**item, **offer, "status": "offer", "matchedBy": "id"} if offer else
                            {**item, "productId": product_id, "title": entry.get("title", ""),
                             "status": "nooffer"})
                continue
            match = choose_product(item["name"], offers, "title")
            if match is not None:
                rows.append({**item, **match, "status": "offer", "matchedBy": "name"})
            else:
                rows.append({**item, "status": "unmapped" if entry.get("checkedAt") else "pending"})
        channels[channel] = {"items": rows, "catalogueOffers": len(offers)}
    return {"checkedAt": catalogue["checkedAt"], "channels": channels}


MAPPING_RECHECK_DAYS = 30


def mapping_candidates(connection, product_map: dict, now: datetime) -> list[tuple[str, dict]]:
    """Names still lacking a product ID, most frequently bought first, channels alternating."""
    queues = []
    for channel, config in CHANNELS.items():
        known = product_map.get(channel, {})
        queue = []
        for item in purchased_items(connection, config["receiptType"], config["receiptMarketId"]):
            entry = known.get(item["name"])
            if entry and entry.get("productId"):
                continue
            if entry and entry.get("checkedAt"):
                try:
                    age = now - datetime.fromisoformat(entry["checkedAt"])
                except (TypeError, ValueError):
                    age = None
                if age is not None and age.days < MAPPING_RECHECK_DAYS:
                    continue
            queue.append((channel, item))
        queues.append(queue)
    ordered = []
    for position in range(max(map(len, queues), default=0)):
        ordered.extend(queue[position] for queue in queues if position < len(queue))
    return ordered


def map_products(candidates: list[tuple[str, dict]], product_map: dict, limit: int,
                 now: datetime, search_fn=None, on_item=None) -> dict:
    """Search single names to learn their product IDs; stop early when REWE throttles."""
    search_fn = search_fn or search
    looked_up = mapped = 0
    consecutive_errors = 0
    paused = False
    for channel, item in candidates[:limit]:
        try:
            row = check_one(item, None, search_fn, channel)
        except ShopThrottled:
            paused = True
            break
        looked_up += 1
        if row["status"] == "error":
            consecutive_errors += 1
            if consecutive_errors >= 3:
                paused = True
                break
            continue
        consecutive_errors = 0
        entry = {"checkedAt": now.isoformat(timespec="seconds"),
                 "productId": row.get("productId") or None, "title": row.get("title") or None}
        product_map.setdefault(channel, {})[item["name"]] = entry
        mapped += bool(entry["productId"])
        if on_item is not None:
            on_item(product_map)
    return {"lookedUp": looked_up, "mapped": mapped, "paused": paused}


def check_one(item: dict, known_id: str | None = None, search_fn=search, channel: str = "market") -> dict:
    result = {**item, "status": "unmapped"}
    try:
        products = search_fn(known_id or item["name"], channel)
        if known_id:
            product = next((p for p in products if str(p.get("id")) == known_id), None)
            if product is None:
                return {**result, "productId": known_id, "status": "unavailable"}
        else:
            product = choose_product(item["name"], products)
        if product is not None:
            result.update(_product_data(product))
    except ShopThrottled as error:
        if error.code != 403:
            raise
        result["status"] = "error"
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        result["status"] = "error"
    return result


def check_items(items: list[dict], known: dict[str, str] | None = None, search_fn=search,
                channel: str = "market") -> dict:
    config = CHANNELS[channel]
    known = known or {}
    rows = []
    paused = False
    consecutive_errors = 0
    for item in items:
        try:
            row = check_one(item, known.get(item["name"]), search_fn, channel)
        except ShopThrottled:
            paused = True
            break
        rows.append(row)
        consecutive_errors = consecutive_errors + 1 if row["status"] == "error" else 0
        if consecutive_errors >= 3:
            paused = True
            break
    return {
        "channel": channel,
        "market": config["label"],
        "marketUrl": config["url"],
        "checkedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "items": rows,
        "paused": paused,
    }


def purchased_items(connection, receipt_type: str = "ebon",
                    receipt_market_id: str | None = None) -> list[dict]:
    rows = connection.execute("""
        SELECT name, purchases, unit_price AS last_price, min_price, last_purchase_date, last_purchase_id
        FROM (
            SELECT i.name, i.unit_price, r.date AS last_purchase_date, i.id AS last_purchase_id,
                   COUNT(*) OVER (PARTITION BY i.name) AS purchases,
                   MIN(i.unit_price) OVER (PARTITION BY i.name) AS min_price,
                   ROW_NUMBER() OVER (PARTITION BY i.name ORDER BY r.date DESC, i.id DESC) AS row_number
            FROM items i JOIN receipts r ON r.id = i.receipt_id
            WHERE r.receipt_type = ? AND (? IS NULL OR r.market_id = ?)
        ) WHERE row_number = 1
        ORDER BY purchases DESC, name
    """, (receipt_type, receipt_market_id, receipt_market_id)).fetchall()
    return [{"name": r[0], "purchases": r[1], "lastPrice": r[2], "minPrice": r[3],
             "lastPurchaseDate": r[4], "lastPurchaseId": r[5]}
            for r in rows if not _EXCLUDE.match(r[0])]
