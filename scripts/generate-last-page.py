#!/usr/bin/env python3
"""Erzeugt die geschützte, mobile Übersicht der jüngsten REWE-Einkäufe."""

from __future__ import annotations

import html
import sqlite3
from datetime import datetime
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_DIR / "rewe_ebons.db"
OUTPUT_PATH = PROJECT_DIR / "web" / "last" / "index.php"
RECEIPT_LIMIT = 25


def euro(value: float | None) -> str:
    return f"{value or 0:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def german_date(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d").strftime("%d.%m.%Y")


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    receipts = conn.execute(
        """
        SELECT id, date, time, market_id, bon_nr, total
        FROM receipts
        ORDER BY date DESC, COALESCE(time, '') DESC, id DESC
        LIMIT ?
        """,
        (RECEIPT_LIMIT,),
    ).fetchall()

    cards: list[str] = []
    for receipt in receipts:
        items = conn.execute(
            """
            SELECT name, price, quantity
            FROM items
            WHERE receipt_id = ?
            ORDER BY id
            """,
            (receipt["id"],),
        ).fetchall()
        item_rows = "".join(
            f"<li><span>{html.escape(item['name'])}"
            f"{f' <small>× {item["quantity"]}</small>' if item['quantity'] not in (None, 1) else ''}"
            f"</span><strong>{euro(item['price'])}</strong></li>"
            for item in items
        ) or "<li><span>Keine Positionen gespeichert</span></li>"
        market = f"Markt {html.escape(receipt['market_id'])}" if receipt["market_id"] else "REWE-Einkauf"
        time = f" · {html.escape(receipt['time'])} Uhr" if receipt["time"] else ""
        cards.append(
            f"""<article class=\"receipt\">
  <header><div><time>{german_date(receipt['date'])}{time}</time><p>{market}</p></div><b>{euro(receipt['total'])}</b></header>
  <ul>{item_rows}</ul>
</article>"""
        )

    updated = datetime.now().strftime("%d.%m.%Y, %H:%M")
    page = f"""<?php
require __DIR__ . '/../auth.php';
require_rewe_login();
?>
<!doctype html>
<html lang=\"de\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <meta name=\"theme-color\" content=\"#cc0000\">
  <title>Letzte Einkäufe · REWE</title>
  <style>
    * {{ box-sizing: border-box; }} body {{ margin:0; background:#f5f6f7; color:#252525; font-family:-apple-system,BlinkMacSystemFont,\"Segoe UI\",sans-serif; }}
    main {{ width:min(100%,760px); margin:0 auto; padding:26px 16px 44px; }} h1 {{ margin:0; font-size:clamp(1.7rem,5vw,2.25rem); letter-spacing:-.04em; }}
    .intro {{ color:#6b7280; margin:7px 0 24px; }} .top {{ display:flex; align-items:center; justify-content:space-between; gap:12px; }}
    .logout {{ color:#555; text-decoration:none; background:#fff; border:1px solid #e2e4e7; border-radius:99px; padding:9px 12px; font-size:.85rem; font-weight:650; white-space:nowrap; }}
    .receipt {{ background:#fff; border:1px solid #e8e9eb; border-radius:17px; margin:12px 0; overflow:hidden; box-shadow:0 2px 8px #00000008; }}
    header {{ display:flex; justify-content:space-between; gap:15px; padding:17px 18px 13px; border-bottom:1px solid #f0f1f2; }} time {{ font-weight:750; font-size:1.05rem; }} header p {{ margin:4px 0 0; color:#7a7f87; font-size:.88rem; }} header b {{ color:#c00; font-size:1.05rem; white-space:nowrap; }}
    ul {{ list-style:none; margin:0; padding:5px 18px 10px; }} li {{ display:flex; justify-content:space-between; gap:14px; padding:8px 0; font-size:.94rem; }} li strong {{ white-space:nowrap; font-weight:650; }} small {{ color:#7a7f87; }}
    footer {{ color:#9aa0a6; text-align:center; font-size:.78rem; margin:24px 0 0; }}
  </style>
</head>
<body><main>
  <div class=\"top\"><h1>Letzte Einkäufe</h1><a class=\"logout\" href=\"/logout.php\">Abmelden</a></div>
  <p class=\"intro\">Die letzten {len(receipts)} REWE-Belege auf einen Blick.</p>
  {''.join(cards)}
  <footer>Zuletzt aktualisiert: {updated}</footer>
</main></body>
</html>"""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(page, encoding="utf-8")
    print(f"{len(receipts)} Belege nach {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
