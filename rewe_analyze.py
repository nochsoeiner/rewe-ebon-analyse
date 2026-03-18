#!/usr/bin/env python3
"""
REWE eBon Analyzer
Extrahiert PDFs aus EML-Dateien, parst Kassenbons und erstellt einen HTML-Analysebericht.
"""

import email
import io
import json
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print("Installiere pdfplumber: pip3 install pdfplumber")
    sys.exit(1)

SCRIPT_DIR  = Path(__file__).parent
IMPORT_DIR  = SCRIPT_DIR / "import"     # EML-Dateien hier ablegen
PDF_DIR     = SCRIPT_DIR / "pdfs"       # auto-extrahierte PDFs
DB_PATH     = SCRIPT_DIR / "rewe_ebons.db"
REPORT_PATH = SCRIPT_DIR / "rewe_report.html"

# ── Kategorien (Keyword-Matching, erster Treffer gewinnt) ──────────────────────
CATEGORIES = {
    'Pfand': ['PFAND'],
    'Obst': [
        'APFEL','BIRNE','BANANE','ORANGE','MANGO','KIWI','TRAUB','ERDBEERE',
        'HEIDELBEERE','HIMBEERE','BROMBEERE','SAUERKIRSCH','KIRSCHE','PFIRSICH',
        'NEKTARINE','PFLAUME','MELONE','ANANAS','ZITRONE','LIMETTE','GRAPEFRUIT',
        'CLEMENTINE','MANDARINE','FEIGE','PAPAYA','AVOCADO','JOHANNISBEER',
        'STACHELBEER','GRANATAPFEL','PASSIONSFR','DATTELN','TULPEN',
        'MIRABELLE','QUITTE','BEERENMIX','BEERENMISCH','OBSTMIX',
        'APRIKOSE','PFLAUMENMUS','APFELMARK','QUETSCHMUS','TRAU.',
    ],
    'Gemüse': [
        'KAROTTE','GURKE','TOMATE','TOM.','CHERRY ROMA','MINI TOMAT','SALAT',
        'PAPRIKA','ZWIEBEL','KNOBLAUCH','BROKKOLI','BROCC','BLUMENKOHL',
        'SPINAT','BABYSPINAT','ZUCCHINI','AUBERGINE','SELLERIE','LAUCH',
        'PORREE','ERBSE','MAIS','KÜRBIS','KURBIS','KOHLRABI','FENCHEL',
        'INGWER','RADISCH','KOHL','ROSENKOHL','WIRSING','CHINAKOHL',
        'FELDSALAT','RUCOLA','MANGOLD','SPARGEL','PILZ','CHAMPIGNON',
        'PFIFFERLING','STEINPILZ','ARTISCHOCKE','ROTE BETE','SÜSSKARTOFFEL',
        'KARTOFFEL','SCHALOTTE','FRÜHLINGSZWIEBEL','SCHNITTLAUCH',
        'PETERSILIE','BASILIKUM','DILL','MINZE','KORIANDER','PAKCHOI',
        'ZWIEBELSCHM','ZWIEBELSCH','ROMARISPENTOM','CORNICHON','STAUDENSEL',
        'WURZELPETER','BEAN','BOHNE',
    ],
    'Fleisch & Wurst': [
        'HACK','RINDER','SCHWEIN','HÄHNCHEN','HÜHNCHEN','HAEHNCHEN','PUTE',
        'LAMM','SALAMI','SCHINKEN','SPECK','BRATWURST','WIENER','MORTADELLA',
        'LEBERWURST','STEAK','SCHNITZEL','GULASCH','FILET','BRATEN',
        'FLEISCH','GEFLÜGEL','GEFLUEGEL','LACHSSCHINKEN','WURST','BIERSCHINKEN',
        'BAERCHENWURST','BACON','CHORIZO','CERVELATWURST','BOCKWURST',
        'FLEISCHWURST','LYONER','BOLOGNA','RINDER PASTE','SALSICCIA',
        'VEG MUEHL','VEG.SPICKER','VEG POMM','VEG. LAND','VEG.LAND',
        'BIO PU ','HAEHNCHENBR','GEFLÜGEL PASTE',
    ],
    'Fisch & Meeresfrüchte': [
        'LACHS','THUNFISCH','HERING','MAKRELE','KABELJAU','SCHOLLE',
        'FORELLE','GARNELE','SHRIMP','SARDINE','MATJES','AAL',
        'DORSCH','SEELACHS','ROTBARSCH',
    ],
    'Milch & Käse & Eier': [
        'MILCH','JOGHURT','QUARK','BUTTER','KÄSE','KAESE','MOZZARELLA','MOZZAR',
        'GOUDA','EDAMER','BRIE','CAMEMBERT','PARMESAN','PARMIGIANO','FRISCHKÄSE',
        'FRISCHKAESE','RAHM','SAHNE','SCHMAND','CREME FRAICH','KEFIR',
        'BUTTERMILCH','SKYR','EIER','STREICHGUT','BERGKAESE','BERGK.',
        'EMMENTAL','ALMETTE','HAVARTI','TILSITER','LEERDAMMER','LEERD.',
        'MANCHEGO','RICOTTA','MASCARPONE','CHEDDAR','GRUYERE','BUTTERK',
        'BUTTERKAESE','FETA','GERAMONT','ELINAS','SALAKIS','FOL EPI',
        'HEFI','GRANA PADANO','GRANA PAD',
    ],
    'Backwaren': [
        'BROT','BROETCHEN','BRÖTCHEN','TOAST','BAGUETTE','CROISSANT',
        'BREZEL','LAUGENBREZEL','MUFFIN','CIABATTA','VOLLKORN','LAUGEN',
        'DINKEL HOERN','HOERNCHEN','ROGGENBR','WEIZENBR','KNÄCKEBROT',
        'KNACKEBROT','PUMPERNICKEL','FLATBREAD','SEMMELKN',
    ],
    'Getränke': [
        'WASSER','SAFT','LIMONADE','COLA','BIER','WEIN','SEKT','PROSECCO',
        'KAFFEE','TEE','ESPRESSO','SMOOTHIE','SCHORLE','ENERGY DRINK',
        'FANTA','SPRITE','MINERALWASSER','TOMATENSAFT','ORANGENSAFT',
        'APFELSAFT','TRAUBENSAFT','MULTIVITAMIN','HAFERD. BARISTA',
        'HAFERMILCH','HAFERD','MANDELMILCH','SOJADRINK','OATLY','AYRAN',
        'KAKAO','HOT CHOC','CHAI','KOMBUCHA',
    ],
    'Tiefkühl': [
        'TK ','TIEFKÜHL','FROZEN','EISCREME','EIS ','EISWÜRFEL',
    ],
    'Süßes & Snacks': [
        'SCHOKO','SCHOKOLADE','KEKS','KUCHEN','TORTE','BONBON',
        'GUMMI','CHIPS','POPCORN','NUSS','MANDEL','CASHEW','ERDNUSS',
        'PRALINE','RIEGEL','WAFFEL','MÜSLIRIEGEL','LECKERMAEULCH',
        'MINI SCHOKO','MUESLIBAR','GRANOLA','MARZIPAN','HALVA',
        'BAIOCCHI','ALTER SCHWEDE','ALMOND','MUESCHELCHEN',
        'DUNKLE SCHOKO','VOLLMILCH SCHOKO','WEISSE SCHOKO',
        'KINDER ','BONNE MAMAN','KONFITURE','KONFITÜRE','MARMELADE',
    ],
    'Grundnahrungsmittel': [
        'MEHL','ZUCKER','SALZ','OLIVENÖL','SPEISEÖL','RAPSÖL','ESSIG',
        'PASTA','NUDEL','FUSILL','PENNE','SPAGHETTI','TAGLIATELLE',
        'REIS','LINSE','KICHERERBSE','HAFERFLOCKEN','MÜSLI','MUESLI',
        'CORNFLAKES','GRIESS','HIRSE','QUINOA','COUSCOUS','POLENTA',
        'BUCHWEIZEN','DINKEL','HAFER','PANIERMEHL','STÄRKE','WEINSTEIN',
        'NATRON','HEFE','BACKPULVER','VANILLE','ZIMT','KARDAMOM',
        'OREGANO','PAPRIKAPULVER','CURRY','KURKUMA','PFEFFERM','MUSKAT',
        'LORBEER','SENF','KETCHUP','MAYONNAISE','SOJASAUCE','WORCESTER',
        'TABASCO','BALSAMICO','PESTO','TOMATENMARK','PASSATA','TORTILLA',
    ],
    'Fertiggerichte & Konserven': [
        'SUPPE','EINTOPF','PIZZA','LASAGNE','BIHUN','KONSERVE',
        'RAVIOLI','TORTELLINI','GNOCCHI','WONTON','TORT. TOM',
        'FRÜHLINGSROLLE','SUSHI','HUMMUS','ANTIPASTI VARIAT',
        'APFEL-ROTKOHL','ROTKOHL','SAUERKRAUT','KICH.-KOK',
        'SEMMELKNÖDEL','POMMES','WK CREMIG',
    ],
    'Körperpflege': [
        'SHAMPOO','DUSCHGEL','DEOS','DEODORANT','ZAHNPASTA','SEIFE',
        'CREME','LOTION','RASIERER','TAMPON','BINDE','WINDEL',
        'SONNENCREME','BODYLOTION','HANDCREME','PFLEGECREME',
        'WATTESTÄBCHEN','WATTESTAEBCHEN','LIPPENPFLEGE',
    ],
    'Haushalt': [
        'SPÜLMITTEL','WASCHMITTEL','PUTZMITTEL','SCHWAMM','KÜCHENROLLE',
        'TOILETTENPAPIER','MÜLLBEUTEL','MUELLBEUTEL','ALUFOLIE',
        'FRISCHHALTEFOLIE','BACKPAPIER','ALLZWECK','MIKROFASER','BÜRSTE',
        'SCHWAMMTUCH','SPÜLBÜRSTE','REINIGER','ENTKALKER','KOMPOSTBEUTEL',
        'ALLZWECKBTL',
    ],
}

def categorize(name: str) -> str:
    """Weist einem Artikelnamen eine Kategorie zu."""
    upper = name.upper()
    for cat, keywords in CATEGORIES.items():
        for kw in keywords:
            if kw in upper:
                return cat
    return 'Sonstiges'

# ── PDF-Text parsen ────────────────────────────────────────────────────────────

ITEM_RE = re.compile(r'^(.+)\s+(\d+,\d{2})\s+([A-Z])\s*\*?\s*$')
MULTI_QTY_RE = re.compile(r'^(\d+)\s+[Ss]tk\s+[xX]\s+(\d+,\d{2})$')
WEIGHT_RE    = re.compile(r'^(\d+[,\.]\d+)\s+kg\s+[xX]\s+([\d,]+)\s+EUR/kg$')
SUMME_RE        = re.compile(r'SUMME\s+EUR\s+(\d+,\d{2})')
DATE_RE         = re.compile(r'(\d{2})\.(\d{1,2})\.(\d{4})\s+(\d{2}):(\d{2})')
MARKT_RE        = re.compile(r'Markt:(\d+)')
BON_RE          = re.compile(r'Bon-Nr\.:(\d+)')
BONUS_EARNED_RE = re.compile(r'hast du (\d+,\d{2}) EUR')
BONUS_BAL_RE    = re.compile(r'Aktuelles Bonus-Guthaben: (\d+,\d{2}) EUR')


def price_to_float(s: str) -> float:
    return float(s.replace(',', '.'))


def parse_receipt(text: str):
    """Parst den Rohtext eines REWE eBon-PDFs."""
    lines = text.splitlines()

    receipt = {
        'date': None, 'time': None, 'market_id': None, 'bon_nr': None,
        'total': None, 'bonus_earned': None, 'bonus_balance': None, 'items': [],
    }

    # Datum, Markt, Bon-Nr., Bonus aus dem gesamten Text holen
    for line in lines:
        if not receipt['date']:
            m = DATE_RE.search(line)
            if m:
                day, mon, year, hour, minute = m.groups()
                receipt['date'] = f"{year}-{int(mon):02d}-{int(day):02d}"
                receipt['time'] = f"{hour}:{minute}"
        if not receipt['market_id']:
            m = MARKT_RE.search(line)
            if m: receipt['market_id'] = m.group(1)
        if not receipt['bon_nr']:
            m = BON_RE.search(line)
            if m: receipt['bon_nr'] = m.group(1)
        if not receipt['total']:
            m = SUMME_RE.search(line)
            if m: receipt['total'] = price_to_float(m.group(1))
        if not receipt['bonus_earned']:
            m = BONUS_EARNED_RE.search(line)
            if m: receipt['bonus_earned'] = price_to_float(m.group(1))
        if not receipt['bonus_balance']:
            m = BONUS_BAL_RE.search(line)
            if m: receipt['bonus_balance'] = price_to_float(m.group(1))

    # Artikel-Block: zwischen "EUR" und "------"
    in_items = False
    pending_item = None  # für Mengenzeilen (N Stk x Preis)

    for line in lines:
        stripped = line.strip()

        if stripped == 'EUR':
            in_items = True
            continue

        if in_items and stripped.startswith('---'):
            break

        if not in_items:
            continue

        # Mengenzeile "2 Stk x 0,39" – kommt NACH dem Artikel
        qty_m = MULTI_QTY_RE.match(stripped)
        if qty_m and pending_item:
            pending_item['quantity'] = int(qty_m.group(1))
            pending_item['unit_price'] = price_to_float(qty_m.group(2))
            # pending_item bleibt offen; nächste Zeile kann weiterer Modifier sein
            continue

        # Gewichtszeile "0,552 kg x 3,99 EUR/kg" – unit_price = EUR/kg
        wt_m = WEIGHT_RE.match(stripped)
        if wt_m:
            if pending_item:
                pending_item['unit_price'] = price_to_float(wt_m.group(2))
            continue

        # Normale Artikelzeile
        item_m = ITEM_RE.match(stripped)
        if item_m:
            if pending_item:
                receipt['items'].append(pending_item)
            name = item_m.group(1).strip()
            price = price_to_float(item_m.group(2))
            tax = item_m.group(3)
            pending_item = {
                'name': name,
                'price': price,
                'tax': tax,
                'quantity': 1,
                'unit_price': price,
            }
            continue

        # Alle anderen Zeilen: pending_item abschließen
        if pending_item:
            receipt['items'].append(pending_item)
            pending_item = None

    if pending_item:
        receipt['items'].append(pending_item)

    if not receipt['date'] or not receipt['items']:
        return None

    return receipt


# ── Datenbank ──────────────────────────────────────────────────────────────────

def init_db(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS receipts (
            id        INTEGER PRIMARY KEY,
            date      TEXT NOT NULL,
            time      TEXT,
            market_id     TEXT,
            bon_nr        TEXT,
            total         REAL,
            source        TEXT,
            bonus_earned  REAL,
            bonus_balance REAL,
            UNIQUE(date, bon_nr, total)
        );
        CREATE TABLE IF NOT EXISTS items (
            id         INTEGER PRIMARY KEY,
            receipt_id INTEGER REFERENCES receipts(id),
            name       TEXT NOT NULL,
            price      REAL NOT NULL,
            unit_price REAL,
            quantity   INTEGER DEFAULT 1,
            tax        TEXT,
            category   TEXT
        );
        CREATE TABLE IF NOT EXISTS processed_files (
            filename TEXT PRIMARY KEY,
            processed_at TEXT DEFAULT (datetime('now'))
        );
    """)
    # Migration: fehlende Spalten ergänzen
    rcols = [r[1] for r in conn.execute("PRAGMA table_info(receipts)")]
    for col in ('bonus_earned', 'bonus_balance'):
        if col not in rcols:
            conn.execute(f"ALTER TABLE receipts ADD COLUMN {col} REAL")
    icols = [r[1] for r in conn.execute("PRAGMA table_info(items)")]
    if 'category' not in icols:
        conn.execute("ALTER TABLE items ADD COLUMN category TEXT")
    conn.commit()
    # Alle Items (neu) kategorisieren – läuft bei jeder DB-Öffnung einmal durch
    rows = conn.execute("SELECT id, name FROM items").fetchall()
    if rows:
        conn.executemany(
            "UPDATE items SET category=? WHERE id=?",
            [(categorize(name), rid) for rid, name in rows]
        )
        conn.commit()


def insert_receipt(conn: sqlite3.Connection, receipt: dict, source: str):
    try:
        cur = conn.execute(
            "INSERT OR IGNORE INTO receipts "
            "(date, time, market_id, bon_nr, total, source, bonus_earned, bonus_balance) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (receipt['date'], receipt['time'], receipt['market_id'], receipt['bon_nr'],
             receipt['total'], source, receipt.get('bonus_earned'), receipt.get('bonus_balance'))
        )
        conn.commit()
        if cur.lastrowid:
            return cur.lastrowid
        row = conn.execute(
            "SELECT id FROM receipts WHERE date=? AND bon_nr=? AND total=?",
            (receipt['date'], receipt['bon_nr'], receipt['total'])
        ).fetchone()
        return row[0] if row else None
    except sqlite3.Error as e:
        print(f"  DB-Fehler Beleg: {e}")
        return None


def insert_items(conn: sqlite3.Connection, receipt_id: int, items: list):
    # Prüfen ob schon vorhanden
    existing = conn.execute(
        "SELECT COUNT(*) FROM items WHERE receipt_id=?", (receipt_id,)
    ).fetchone()[0]
    if existing:
        return
    conn.executemany(
        "INSERT INTO items (receipt_id, name, price, unit_price, quantity, tax, category) "
        "VALUES (?,?,?,?,?,?,?)",
        [(receipt_id, i['name'], i['price'], i['unit_price'], i['quantity'], i['tax'],
          categorize(i['name']))
         for i in items]
    )
    conn.commit()


# ── EML verarbeiten ────────────────────────────────────────────────────────────

def process_eml(path: Path, conn: sqlite3.Connection) -> bool:
    with open(path, 'rb') as f:
        msg = email.message_from_bytes(f.read())

    for part in msg.walk():
        fname = part.get_filename() or ''
        if not fname.lower().endswith('.pdf'):
            continue
        pdf_data = part.get_payload(decode=True)
        if not pdf_data:
            continue
        try:
            with pdfplumber.open(io.BytesIO(pdf_data)) as pdf:
                text = '\n'.join(p.extract_text() or '' for p in pdf.pages)
        except Exception as e:
            print(f"  PDF-Fehler in {path.name}: {e}")
            return False

        receipt = parse_receipt(text)
        if not receipt:
            print(f"  Konnte Beleg nicht parsen: {path.name}")
            return False

        rid = insert_receipt(conn, receipt, path.name)
        if rid:
            insert_items(conn, rid, receipt['items'])
        # Als verarbeitet markieren
        conn.execute(
            "INSERT OR IGNORE INTO processed_files (filename) VALUES (?)", (path.name,)
        )
        conn.commit()
        return True
    return False


# ── PDF-Extraktion ─────────────────────────────────────────────────────────────

def extract_all_pdfs():
    """Extrahiert PDFs aus EMLs und kopiert direkte PDFs in den pdfs/-Ordner."""
    import shutil
    PDF_DIR.mkdir(exist_ok=True)
    # EMLs → PDFs extrahieren
    for path in sorted(IMPORT_DIR.glob("*.eml")):
        pdf_out = PDF_DIR / (path.stem + ".pdf")
        if pdf_out.exists():
            continue
        try:
            with open(path, 'rb') as f:
                msg = email.message_from_bytes(f.read())
            for part in msg.walk():
                fname = part.get_filename() or ''
                if fname.lower().endswith('.pdf'):
                    data = part.get_payload(decode=True)
                    if data:
                        pdf_out.write_bytes(data)
                    break
        except Exception:
            pass
    # Direkte PDFs aus import/ → pdfs/ kopieren
    for path in sorted(IMPORT_DIR.glob("*.pdf")):
        pdf_out = PDF_DIR / path.name
        if not pdf_out.exists():
            shutil.copy2(path, pdf_out)


def process_pdf_direct(path: Path, conn: sqlite3.Connection) -> bool:
    """Verarbeitet eine direkt abgelegte PDF-Datei aus dem Import-Ordner."""
    pdf_dest = PDF_DIR / path.name
    try:
        with pdfplumber.open(pdf_dest) as pdf:
            text = '\n'.join(p.extract_text() or '' for p in pdf.pages)
    except Exception as e:
        print(f"  PDF-Fehler in {path.name}: {e}")
        return False

    receipt = parse_receipt(text)
    if not receipt or not receipt.get('date') or not receipt.get('total'):
        print(f"  Konnte Beleg nicht parsen: {path.name}")
        return False

    rid = insert_receipt(conn, receipt, path.name)
    if rid:
        insert_items(conn, rid, receipt['items'])
    conn.execute(
        "INSERT OR IGNORE INTO processed_files (filename) VALUES (?)", (path.name,)
    )
    conn.commit()
    return True


def backfill_bonus(conn: sqlite3.Connection):
    """Liest Bonus-Daten aus gespeicherten PDFs für Belege nach, wo es noch fehlt."""
    rows = conn.execute(
        "SELECT id, source FROM receipts WHERE bonus_earned IS NULL"
    ).fetchall()
    updates = []
    for rid, source in rows:
        pdf_path = PDF_DIR / source.replace('.eml', '.pdf')
        if not pdf_path.exists():
            continue
        try:
            with pdfplumber.open(pdf_path) as pdf:
                text = '\n'.join(p.extract_text() or '' for p in pdf.pages)
        except Exception:
            continue
        me = BONUS_EARNED_RE.search(text)
        mb = BONUS_BAL_RE.search(text)
        if me or mb:
            updates.append((
                price_to_float(me.group(1)) if me else None,
                price_to_float(mb.group(1)) if mb else None,
                rid,
            ))
    if updates:
        conn.executemany(
            "UPDATE receipts SET bonus_earned=?, bonus_balance=? WHERE id=?", updates
        )
        conn.commit()


# ── HTML-Report ────────────────────────────────────────────────────────────────

def generate_report(conn: sqlite3.Connection):
    from collections import defaultdict

    def fmt(v):
        """Float → '1.234,56'"""
        if v is None: return '–'
        return f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')

    def feur(v):
        return f'€\u00a0{fmt(v)}'

    # ── Daten abfragen ──────────────────────────────────────────────────────

    stats = conn.execute("""
        SELECT COUNT(*), ROUND(SUM(total),2), ROUND(AVG(total),2),
               MIN(date), MAX(date)
        FROM receipts
    """).fetchone()

    monthly = conn.execute("""
        SELECT substr(date,1,7), COUNT(*), ROUND(SUM(total),2)
        FROM receipts GROUP BY 1 ORDER BY 1
    """).fetchall()

    yearly = conn.execute("""
        SELECT substr(date,1,4), COUNT(*), ROUND(SUM(total),2), ROUND(AVG(total),2)
        FROM receipts GROUP BY 1 ORDER BY 1
    """).fetchall()

    # Alle Artikel-Namen (für Preisentwicklungs-Picker), nach Häufigkeit
    all_item_names = conn.execute("""
        SELECT name, COUNT(*) as cnt FROM items GROUP BY name ORDER BY cnt DESC
    """).fetchall()

    # Preisentwicklung: alle Artikel, alle Monate
    price_raw = conn.execute("""
        SELECT i.name, substr(r.date,1,7), ROUND(AVG(i.unit_price),2)
        FROM items i JOIN receipts r ON i.receipt_id=r.id
        GROUP BY i.name, substr(r.date,1,7)
        ORDER BY i.name, substr(r.date,1,7)
    """).fetchall()

    price_by_item = defaultdict(dict)
    price_months = set()
    for name, month, avg in price_raw:
        price_by_item[name][month] = avg
        price_months.add(month)
    price_months = sorted(price_months)

    # Top-30 nach Häufigkeit
    top_freq = conn.execute("""
        SELECT name, COUNT(*) cnt, ROUND(SUM(price),2), ROUND(AVG(unit_price),2),
               ROUND(MIN(unit_price),2), ROUND(MAX(unit_price),2)
        FROM items GROUP BY name ORDER BY cnt DESC LIMIT 30
    """).fetchall()

    # Top-20 nach Ausgaben
    top_spend = conn.execute("""
        SELECT name, ROUND(SUM(price),2) tot, COUNT(*) cnt
        FROM items GROUP BY name ORDER BY tot DESC LIMIT 20
    """).fetchall()

    # Kategorien: Ausgaben + Häufigkeit
    cat_stats = conn.execute("""
        SELECT COALESCE(category,'Sonstiges'), ROUND(SUM(price),2), COUNT(*)
        FROM items GROUP BY 1 ORDER BY 2 DESC
    """).fetchall()

    # Alle Positionen (für Such-Tab)
    all_items = conn.execute("""
        SELECT i.name, i.price, i.unit_price, i.quantity, r.date, r.source,
               COALESCE(i.category,'Sonstiges')
        FROM items i JOIN receipts r ON i.receipt_id=r.id
        ORDER BY r.date DESC, i.name
    """).fetchall()

    # Alle Belege (für Belege-Tab) – inkl. Items für expandierbare Zeilen
    all_receipts = conn.execute("""
        SELECT r.id, r.date, r.time, r.total, r.bon_nr,
               COUNT(i.id) as item_cnt, r.source,
               r.bonus_earned, r.bonus_balance
        FROM receipts r LEFT JOIN items i ON i.receipt_id=r.id
        GROUP BY r.id ORDER BY r.date DESC
    """).fetchall()

    # Items pro Beleg (für expandierbare Zeilen)
    items_by_src = defaultdict(list)
    for row in all_items:
        items_by_src[row[5]].append(row)  # row[5] = source

    # Wochentag-Analyse
    weekday_raw = conn.execute("""
        SELECT CAST(strftime('%w', date) AS INT) as dow,
               COUNT(*) trips, ROUND(AVG(total),2) avg_total,
               ROUND(SUM(total),2) sum_total
        FROM receipts GROUP BY dow ORDER BY dow
    """).fetchall()
    DOW_NAMES = ['Sonntag','Montag','Dienstag','Mittwoch','Donnerstag','Freitag','Samstag']
    weekday_data = {r[0]: r for r in weekday_raw}
    weekday_full = [(DOW_NAMES[i], *weekday_data.get(i, (i, 0, 0.0, 0.0))[1:])
                    for i in range(7)]

    # Inflations-Tracker: erste vs. letzte bekannte Preis (min. 3 Käufe)
    from itertools import groupby as _groupby
    inf_raw = conn.execute("""
        SELECT i.name, r.date, i.unit_price
        FROM items i JOIN receipts r ON i.receipt_id=r.id
        WHERE i.unit_price > 0
          AND i.name IN (SELECT name FROM items GROUP BY name HAVING COUNT(*)>=3)
        ORDER BY i.name, r.date
    """).fetchall()
    inflation = []
    for name, rows in _groupby(inf_raw, key=lambda r: r[0]):
        rows = list(rows)
        fd, fp = rows[0][1], rows[0][2]
        ld, lp = rows[-1][1], rows[-1][2]
        if fp and fp > 0 and lp != fp:
            inflation.append((name, fd, fp, ld, lp,
                               round((lp - fp) / fp * 100, 1), len(rows)))
    inflation.sort(key=lambda r: r[5], reverse=True)

    # Bonus-Statistik
    bonus_monthly = conn.execute("""
        SELECT substr(date,1,7),
               ROUND(SUM(bonus_earned),2)                         as earned,
               MAX(bonus_balance)                                  as balance,
               ROUND(SUM(total),2)                                as umsatz,
               ROUND(SUM(bonus_earned)/SUM(total)*100, 2)         as pct
        FROM receipts WHERE bonus_earned IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """).fetchall()
    bonus_total = conn.execute("""
        SELECT ROUND(SUM(bonus_earned),2),
               (SELECT bonus_balance FROM receipts
                WHERE bonus_balance IS NOT NULL ORDER BY date DESC LIMIT 1),
               ROUND(SUM(bonus_earned)/NULLIF(SUM(CASE WHEN bonus_earned IS NOT NULL
                     THEN total END),0)*100, 2)
        FROM receipts
    """).fetchone()

    # ── JSON für JavaScript ─────────────────────────────────────────────────

    month_labels_js = json.dumps([m for m,_,_ in monthly])
    month_data_js   = json.dumps([float(t) for _,_,t in monthly])

    # Preisentwicklungs-Daten: {itemName: {month: price, ...}, ...}
    price_data_js = json.dumps({
        name: {m: price_by_item[name].get(m) for m in price_months}
        for name, _ in all_item_names
    })
    price_months_js = json.dumps(price_months)

    # Top-10 Namen für Standardauswahl
    default_items_js = json.dumps([n for n,_ in all_item_names[:10]])

    # Kategorie-Donut-Daten
    cat_labels_js = json.dumps([r[0] for r in cat_stats])
    cat_data_js   = json.dumps([float(r[1]) for r in cat_stats])
    cat_colors = [
        '#2a9d8f','#4caf50','#e63946','#e9c46a','#457b9d',
        '#f4a261','#264653','#9b2226','#6d6875','#b5838d',
        '#52b788','#e76f51','#0077b6','#a7c957','#c77dff',
    ]
    cat_colors_js = json.dumps((cat_colors * 3)[:len(cat_stats)])

    # Alle Positionen als JSON für Suche
    items_js = json.dumps([
        {
            'n': row[0],
            'p': row[1],
            'u': row[2],
            'q': row[3],
            'd': row[4],
            'src': row[5],
            'cat': row[6],
        }
        for row in all_items
    ], ensure_ascii=False)

    # Alle Belege als JSON – mit eingebetteten Items für Aufklapp-Funktion
    receipts_js = json.dumps([
        {
            'date': row[1],
            'time': row[2] or '',
            'total': row[3],
            'bon': row[4] or '',
            'itemCnt': row[5],
            'src': row[6],
            'pdf': 'pdfs/' + row[6].replace('.eml', '.pdf'),
            'bonus': row[7],
            'lines': [
                {'n': i[0], 'p': i[1], 'u': i[2], 'q': i[3], 'cat': i[6]}
                for i in items_by_src.get(row[6], [])
            ],
        }
        for row in all_receipts
    ], ensure_ascii=False)

    # Wochentag-JSON
    weekday_labels_js = json.dumps([r[0] for r in weekday_full])
    weekday_trips_js  = json.dumps([r[1] for r in weekday_full])
    weekday_avg_js    = json.dumps([float(r[2]) if r[2] else 0 for r in weekday_full])

    # Inflations-JSON (Top 25 Anstiege + Top 10 Senkungen)
    # Alle Artikel mit Preisänderung – als JSON für JS-Filter
    inflation_all = inflation  # bereits nach pct desc sortiert

    # Bonus-JSON
    bonus_months_js   = json.dumps([r[0] for r in bonus_monthly])
    bonus_earned_js   = json.dumps([float(r[1]) if r[1] else 0  for r in bonus_monthly])
    bonus_balance_js  = json.dumps([float(r[2]) if r[2] else None for r in bonus_monthly])
    bonus_pct_js      = json.dumps([float(r[4]) if r[4] else None for r in bonus_monthly])
    bonus_total_earned = bonus_total[0] or 0
    bonus_current_bal  = bonus_total[1] or 0
    bonus_avg_pct      = bonus_total[2] or 0

    # ── HTML-Tabellen ───────────────────────────────────────────────────────

    import re as _re
    _NUM_RE = _re.compile(
        r'^[€\+\-]?\s*[\d\.,]+\s*[€%×]?$'    # Zahlen, Preise, Prozent, Menge
        r'|^\d{2}\.\d{2}\.\d{4}$'              # DD.MM.YYYY
        r'|^\d{4}-\d{2}(-\d{2})?$'             # YYYY-MM oder YYYY-MM-DD
        r'|^\d{2}:\d{2}$'                       # HH:MM
        r'|^\d{4}$'                             # Jahreszahl
    )

    def tr(cells, tag='td'):
        parts = []
        for c in cells:
            # \u00a0 (geschütztes Leerzeichen aus feur()) vor dem Match normalisieren
            plain = _re.sub(r'<[^>]+>', '', str(c)).strip().replace('\u00a0', ' ')
            is_num = tag == 'td' and bool(_NUM_RE.match(plain)) and plain not in ('', '–', '-')
            cls = ' class="num"' if is_num else ''
            parts.append(f'<{tag}{cls}>{c}</{tag}>')
        return '<tr>' + ''.join(parts) + '</tr>'

    yearly_rows = ''.join(
        tr([y, t, feur(tot), feur(avg)])
        for y, t, tot, avg in yearly
    )
    monthly_rows = ''.join(
        tr([m, t, feur(tot)])
        for m, t, tot in monthly
    )
    top_freq_rows = ''.join(
        tr([n, c, feur(ts), feur(ap), feur(mn), feur(mx)])
        for n, c, ts, ap, mn, mx in top_freq
    )
    top_spend_rows = ''.join(
        tr([n, feur(tot), c])
        for n, tot, c in top_spend
    )

    avg_per_month = feur(stats[1] / max(len(monthly), 1))
    now_str = datetime.now().strftime('%d.%m.%Y %H:%M')

    def iso_de(s):
        """'2024-12-12' → '12.12.2024'"""
        if not s: return ''
        parts = s.split('-')
        return f"{parts[2]}.{parts[1]}.{parts[0]}" if len(parts) == 3 else s

    def pct_cell(v):
        cls = 'pct-pos' if v > 0 else 'pct-neg'
        sign = '+' if v > 0 else ''
        return f'<span class="{cls}">{sign}{fmt(v)} %</span>'

    # Inflation-JSON für JS-Tabelle
    inflation_js = json.dumps([
        {'n': n, 'fd': iso_de(fd), 'fp': fp, 'ld': iso_de(ld), 'lp': lp, 'pct': pct, 'cnt': c}
        for n, fd, fp, ld, lp, pct, c in inflation_all
    ], ensure_ascii=False)

    weekday_rows = ''.join(
        tr([name, trips, feur(avg_t), feur(sum_t)])
        for name, trips, avg_t, sum_t in weekday_full
    )

    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>REWE eBon Analyse</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f0f2f5;color:#1a1a2e}}
a{{color:#cc0000;text-decoration:none}}a:hover{{text-decoration:underline}}
header{{background:#cc0000;color:#fff;padding:1.2rem 2rem;display:flex;align-items:center;gap:1rem}}
header h1{{font-size:1.6rem;flex:1}}
header p{{opacity:.8;font-size:.9rem}}
nav{{background:#fff;border-bottom:2px solid #cc0000;position:sticky;top:0;z-index:100}}
nav button{{background:none;border:none;padding:.8rem 1.4rem;font-size:.95rem;cursor:pointer;
           border-bottom:3px solid transparent;color:#555;transition:.15s}}
nav button.active{{color:#cc0000;border-bottom-color:#cc0000;font-weight:600}}
.page{{display:none}}.page.active{{display:block}}
.container{{max-width:1200px;margin:2rem auto;padding:0 1rem}}
.stats-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:1rem;margin-bottom:2rem}}
.stat{{background:#fff;border-radius:12px;padding:1.2rem;text-align:center;box-shadow:0 2px 8px #0001}}
.stat .val{{font-size:1.8rem;font-weight:700;color:#cc0000}}
.stat .lbl{{font-size:.8rem;color:#777;margin-top:.3rem}}
section{{background:#fff;border-radius:12px;padding:1.5rem;box-shadow:0 2px 8px #0001;margin-bottom:1.5rem}}
section h2{{font-size:1.1rem;color:#cc0000;margin-bottom:1rem;border-bottom:2px solid #cc000022;padding-bottom:.4rem}}
.chart-wrap{{position:relative;height:300px}}
table{{width:100%;border-collapse:collapse;font-size:.88rem}}
th{{background:#cc0000;color:#fff;padding:.55rem .8rem;text-align:left;white-space:nowrap;
    user-select:none}}
th.sortable{{cursor:pointer}}
th.sortable:hover{{background:#aa0000}}
th.sort-asc::after{{content:' ▲';font-size:.7em}}
th.sort-desc::after{{content:' ▼';font-size:.7em}}
.num{{text-align:right}}
td{{padding:.45rem .8rem;border-bottom:1px solid #eee}}
tr:hover td{{background:#fff5f5}}
.expand-row td{{background:#fafafa;padding:.3rem .8rem .8rem 2rem;border-bottom:2px solid #eee}}
.expand-row table{{font-size:.82rem;margin-top:.3rem}}
.expand-row th{{background:#cc000022;color:#cc0000;padding:.3rem .6rem}}
.expand-toggle{{cursor:pointer;font-size:.8rem;color:#999;margin-left:.4rem}}
tr.expandable-row:hover .expand-toggle{{color:#cc0000}}
.pct-pos{{color:#cc0000;font-weight:600}}
.pct-neg{{color:#2a9d8f;font-weight:600}}
.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:1.5rem}}
@media(max-width:700px){{.two-col{{grid-template-columns:1fr}}}}
input[type=text],input[type=search]{{width:100%;padding:.5rem .8rem;border:1px solid #ddd;
  border-radius:6px;font-size:.9rem;margin-bottom:.8rem}}
input:focus{{outline:2px solid #cc000066;border-color:#cc0000}}
.scroll{{max-height:420px;overflow-y:auto}}
.badge{{display:inline-block;background:#cc000015;color:#cc0000;border-radius:4px;
        padding:.1rem .45rem;font-size:.78rem;font-weight:600}}
#trend-picker{{display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:1rem;
               max-height:160px;overflow-y:auto;border:1px solid #eee;border-radius:8px;padding:.5rem}}
#trend-picker label{{display:flex;align-items:center;gap:.3rem;font-size:.82rem;cursor:pointer;
                     background:#f9f9f9;border:1px solid #ddd;border-radius:5px;padding:.2rem .5rem}}
#trend-picker label:hover{{background:#fff0f0;border-color:#cc0000}}
#trend-picker input{{accent-color:#cc0000}}
.ctrl-btn{{background:#f5f5f5;border:1px solid #ddd;border-radius:6px;padding:.4rem .8rem;
           cursor:pointer;font-size:.85rem;white-space:nowrap}}
.ctrl-btn:hover{{background:#fff0f0;border-color:#cc0000;color:#cc0000}}
.ctrl-btn.inf-active{{background:#cc0000;color:#fff;border-color:#cc0000}}
#items-count{{font-size:.82rem;color:#888;margin-bottom:.5rem}}
.pdf-link{{display:inline-flex;align-items:center;gap:.2rem;font-size:.82rem}}
footer{{text-align:center;padding:2rem;color:#aaa;font-size:.78rem}}
</style>
</head>
<body>
<header>
  <div>
    <h1>🛒 REWE eBon Analyse</h1>
    <p>Erstellt {now_str} &mdash; {iso_de(stats[3])} bis {iso_de(stats[4])}</p>
  </div>
</header>

<nav>
  <button class="active" onclick="showTab('dashboard')">Dashboard</button>
  <button onclick="showTab('trends')">Preisentwicklung</button>
  <button onclick="showTab('stats')">Statistiken</button>
  <button onclick="showTab('positions')">Alle Positionen</button>
  <button onclick="showTab('receipts')">Alle Belege</button>
</nav>

<!-- ═══════════════════════════════════════════ DASHBOARD ═══ -->
<div id="page-dashboard" class="page active">
<div class="container">
  <div class="stats-grid">
    <div class="stat"><div class="val">{stats[0]}</div><div class="lbl">Einkäufe</div></div>
    <div class="stat"><div class="val">{feur(stats[1])}</div><div class="lbl">Gesamtausgaben</div></div>
    <div class="stat"><div class="val">{feur(stats[2])}</div><div class="lbl">Ø pro Einkauf</div></div>
    <div class="stat"><div class="val">{avg_per_month}</div><div class="lbl">Ø pro Monat</div></div>
  </div>

  <section>
    <h2>Monatliche Ausgaben</h2>
    <div class="chart-wrap" style="height:320px"><canvas id="monthChart"></canvas></div>
  </section>

  <div class="two-col">
    <section>
      <h2>Ausgaben nach Kategorie</h2>
      <div class="chart-wrap" style="height:280px"><canvas id="catChart"></canvas></div>
    </section>
    <section>
      <h2>Jahresübersicht</h2>
      <table>
        <thead>{tr(['Jahr','Einkäufe','Gesamt','Ø/Einkauf'],'th')}</thead>
        <tbody>{yearly_rows}</tbody>
      </table>
    </section>
  </div>

  <div class="two-col">
    <section>
      <h2>Häufigste Artikel (Top 30)</h2>
      <div class="scroll">
      <table>
        <thead>{tr(['Artikel','Käufe','Gesamt','Ø Preis','Min','Max'],'th')}</thead>
        <tbody>{top_freq_rows}</tbody>
      </table>
      </div>
    </section>
    <section>
      <h2>Höchste Gesamtausgaben (Top 20)</h2>
      <div class="scroll">
      <table>
        <thead>{tr(['Artikel','Ausgaben','Käufe'],'th')}</thead>
        <tbody>{top_spend_rows}</tbody>
      </table>
      </div>
    </section>
  </div>
</div>
</div>

<!-- ═══════════════════════════════════════════ PREISENTWICKLUNG ═══ -->
<div id="page-trends" class="page">
<div class="container">
  <section>
    <h2>Preisentwicklung – Artikel auswählen</h2>
    <div style="display:flex;gap:.5rem;align-items:center;margin-bottom:.5rem;flex-wrap:wrap">
      <input type="search" id="trend-search" placeholder="Artikel filtern…"
             oninput="filterPicker()" style="flex:1;min-width:180px;margin:0">
      <button class="ctrl-btn" onclick="selectAll(true)">Alle</button>
      <button class="ctrl-btn" onclick="selectAll(false)">Keine</button>
      <button class="ctrl-btn" onclick="selectTop10()">Top 10</button>
    </div>
    <div id="trend-picker"></div>
    <div class="chart-wrap" style="height:420px"><canvas id="trendChart"></canvas></div>
  </section>
</div>
</div>

<!-- ═══════════════════════════════════════════ STATISTIKEN ═══ -->
<div id="page-stats" class="page">
<div class="container">

  <div class="two-col">
    <section>
      <h2>Einkäufe nach Wochentag</h2>
      <div class="chart-wrap"><canvas id="weekdayChart"></canvas></div>
    </section>
    <section>
      <h2>Wochentag-Details</h2>
      <table>
        <thead>{tr(['Tag','Einkäufe','Ø Betrag','Gesamt'],'th')}</thead>
        <tbody>{weekday_rows}</tbody>
      </table>
    </section>
  </div>

  <section>
    <h2>Bonus-Guthaben</h2>
    <div class="stats-grid" style="margin-bottom:1rem">
      <div class="stat"><div class="val">{feur(bonus_total_earned)}</div>
           <div class="lbl">Gesamt gesammelt</div></div>
      <div class="stat"><div class="val">{feur(bonus_current_bal)}</div>
           <div class="lbl">Aktuelles Guthaben</div></div>
      <div class="stat"><div class="val">{fmt(bonus_avg_pct)} %</div>
           <div class="lbl">Ø Bonus-Rate</div></div>
    </div>
    <div class="two-col">
      <div>
        <div style="font-size:.85rem;color:#777;margin-bottom:.4rem">Gesammelt &amp; Guthaben</div>
        <div class="chart-wrap"><canvas id="bonusChart"></canvas></div>
      </div>
      <div>
        <div style="font-size:.85rem;color:#777;margin-bottom:.4rem">Bonus-Rate pro Monat (% des Umsatzes)</div>
        <div class="chart-wrap"><canvas id="bonusPctChart"></canvas></div>
      </div>
    </div>
  </section>

  <section>
    <h2>Preisentwicklung je Artikel</h2>
    <div style="display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:.8rem;align-items:center">
      <button class="ctrl-btn inf-active" onclick="filterInflation('all',this)">Alle</button>
      <button class="ctrl-btn" onclick="filterInflation('up',this)">▲ Preissteigerungen</button>
      <button class="ctrl-btn" onclick="filterInflation('down',this)">▼ Preissenkungen</button>
      <span id="inf-count" style="margin-left:auto;font-size:.82rem;color:#888"></span>
    </div>
    <div class="scroll" style="max-height:520px">
    <table id="inf-table">
      <thead><tr>
        <th>Artikel</th>
        <th class="num">Erst-Datum</th><th class="num">Erst-Preis</th>
        <th class="num">Letzt-Datum</th><th class="num">Letzt-Preis</th>
        <th class="num">Änderung</th><th class="num">Käufe</th>
      </tr></thead>
      <tbody id="inf-body"></tbody>
    </table>
    </div>
  </section>

</div>
</div>

<!-- ═══════════════════════════════════════════ ALLE POSITIONEN ═══ -->
<div id="page-positions" class="page">
<div class="container">
  <section>
    <h2>Alle Positionen</h2>
    <div style="display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:.5rem">
      <input type="search" id="pos-search" placeholder="Artikel suchen…"
             oninput="filterPositions()" style="flex:1;min-width:180px;margin:0">
      <select id="pos-cat" onchange="filterPositions()"
              style="padding:.45rem .7rem;border:1px solid #ddd;border-radius:6px;font-size:.9rem">
        <option value="">Alle Kategorien</option>
        {chr(10).join(f'<option>{c}</option>' for c in sorted(set(r[0] for r in cat_stats)))}
      </select>
    </div>
    <div id="items-count"></div>
    <div class="scroll" style="max-height:600px">
    <table id="pos-table">
      <thead>
        <tr>
          <th class="sortable sort-desc" data-key="d" onclick="sortPositions(this)">Datum</th>
          <th class="sortable" data-key="n" onclick="sortPositions(this)">Artikel</th>
          <th class="sortable" data-key="cat" onclick="sortPositions(this)">Kategorie</th>
          <th class="sortable num" data-key="p" onclick="sortPositions(this)">Preis</th>
          <th class="sortable num" data-key="u" onclick="sortPositions(this)">Einzelpreis</th>
          <th class="sortable num" data-key="q" onclick="sortPositions(this)">Menge</th>
          <th>PDF</th>
        </tr>
      </thead>
      <tbody id="pos-body"></tbody>
    </table>
    </div>
  </section>
</div>
</div>

<!-- ═══════════════════════════════════════════ ALLE BELEGE ═══ -->
<div id="page-receipts" class="page">
<div class="container">
  <section>
    <h2>Alle Belege</h2>
    <input type="search" id="rec-search" placeholder="Datum oder Bon-Nr suchen…" oninput="filterReceipts()">
    <div class="scroll" style="max-height:700px">
    <table id="rec-table">
      <thead><tr>
        <th style="width:1.5rem"></th>
        <th class="sortable sort-desc" data-key="date" onclick="sortReceipts(this)">Datum</th>
        <th class="sortable" data-key="time" onclick="sortReceipts(this)">Uhrzeit</th>
        <th class="sortable num" data-key="total" onclick="sortReceipts(this)">Summe</th>
        <th class="sortable num" data-key="itemCnt" onclick="sortReceipts(this)">Artikel</th>
        <th class="sortable num" data-key="bonus" onclick="sortReceipts(this)">Bonus</th>
        <th>PDF</th>
      </tr></thead>
      <tbody id="rec-body"></tbody>
    </table>
    </div>
  </section>
</div>
</div>

<footer>REWE eBon Analyse &bull; {stats[0]} Kassenbons &bull; {len(all_items)} Positionen</footer>

<script>
// ── Daten ──────────────────────────────────────────────────────────────────
const MONTHS          = {price_months_js};
const PRICE_DATA      = {price_data_js};
const DEF_ITEMS       = {default_items_js};
const ALL_ITEMS       = {items_js};
const ALL_RCPTS       = {receipts_js};
const CAT_LABELS      = {cat_labels_js};
const CAT_DATA        = {cat_data_js};
const CAT_COLORS      = {cat_colors_js};
const WEEKDAY_LABELS  = {weekday_labels_js};
const WEEKDAY_TRIPS   = {weekday_trips_js};
const WEEKDAY_AVG     = {weekday_avg_js};
const BONUS_MONTHS    = {bonus_months_js};
const BONUS_EARNED    = {bonus_earned_js};
const BONUS_BALANCE   = {bonus_balance_js};
const BONUS_PCT       = {bonus_pct_js};
const INFLATION       = {inflation_js};

// ── Navigation ─────────────────────────────────────────────────────────────
function showTab(id) {{
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('nav button').forEach(b => b.classList.remove('active'));
  document.getElementById('page-' + id).classList.add('active');
  event.target.classList.add('active');
  if (id === 'trends'    && !window._trendInit) initTrends();
  if (id === 'stats'     && !window._statsInit) initStats();
  if (id === 'positions' && !window._posInit)   initPositions();
  if (id === 'receipts'  && !window._recInit)   initReceipts();
}}

// ── Hilfsfunktionen ─────────────────────────────────────────────────────────

// Richtet th-Zellen rechtsbündig aus, wenn die zugehörige Datenspalte .num hat
function alignHeaders(table) {{
  if (typeof table === 'string') table = document.getElementById(table);
  if (!table) return;
  const ths = Array.from(table.querySelectorAll('thead th'));
  const firstRow = table.querySelector('tbody tr');
  if (!firstRow) return;
  Array.from(firstRow.querySelectorAll('td')).forEach((td, i) => {{
    if (td.classList.contains('num') && ths[i]) ths[i].classList.add('num');
  }});
}}

// Alle statischen Tabellen beim Laden ausrichten
document.addEventListener('DOMContentLoaded', () => {{
  document.querySelectorAll('table').forEach(alignHeaders);
}});

function eur(v) {{
  if (v == null) return '–';
  return '€\u00a0' + v.toFixed(2).replace('.', ',');
}}
function isoDE(s) {{
  if (!s) return '';
  const p = s.split('-');
  return p.length === 3 ? p[2] + '.' + p[1] + '.' + p[0] : s;
}}

// ── Dashboard: Monats-Chart mit Jahres-Trennstrichen ───────────────────────
const yearSepPlugin = {{
  id: 'yearSep',
  afterDraw(chart) {{
    const {{ctx, chartArea, scales}} = chart;
    const labels = chart.data.labels;
    if (!labels || !scales.x) return;
    ctx.save();
    ctx.strokeStyle = '#88888866';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([5, 4]);
    ctx.font = 'bold 11px sans-serif';
    ctx.fillStyle = '#999';
    ctx.textAlign = 'left';
    labels.forEach((label, i) => {{
      if (i === 0) return;
      if (label.slice(0,4) !== labels[i-1].slice(0,4)) {{
        // Mitte zwischen zwei Balken
        const xPrev = scales.x.getPixelForValue(i - 1);
        const xCurr = scales.x.getPixelForValue(i);
        const x = (xPrev + xCurr) / 2;
        ctx.beginPath();
        ctx.moveTo(x, chartArea.top);
        ctx.lineTo(x, chartArea.bottom);
        ctx.stroke();
        ctx.fillText(label.slice(0,4), x + 4, chartArea.top + 13);
      }}
    }});
    ctx.restore();
  }}
}};

new Chart(document.getElementById('monthChart'), {{
  type: 'bar',
  plugins: [yearSepPlugin],
  data: {{
    labels: {month_labels_js},
    datasets: [{{
      label: 'Ausgaben',
      data: {month_data_js},
      backgroundColor: 'rgba(204,0,0,0.55)',
      borderColor: '#cc0000',
      borderWidth: 1.5,
      borderRadius: 4,
    }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{ y: {{ ticks: {{ callback: v => '€ ' + v.toFixed(0) }} }} }}
  }}
}});

// ── Dashboard: Kategorie-Donut ──────────────────────────────────────────────
new Chart(document.getElementById('catChart'), {{
  type: 'doughnut',
  data: {{
    labels: CAT_LABELS,
    datasets: [{{ data: CAT_DATA, backgroundColor: CAT_COLORS, borderWidth: 1 }}]
  }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      legend: {{ position: 'right', labels: {{
        boxWidth: 12, font: {{ size: 11 }},
        formatter: (label, ctx) => {{
          const v = ctx.dataset.data[ctx.dataIndex];
          return label + '  ' + v.toFixed(2).replace('.',',') + ' €';
        }}
      }} }}
    }}
  }}
}});

// ── Preisentwicklung ────────────────────────────────────────────────────────
const COLORS = ['#e63946','#457b9d','#2a9d8f','#e9c46a','#f4a261',
                '#264653','#6d6875','#b5838d','#e76f51','#52b788',
                '#9b2226','#0077b6','#023e8a','#d62828','#a7c957'];
let trendChart = null;

function buildPicker(filter='') {{
  const div = document.getElementById('trend-picker');
  const names = Object.keys(PRICE_DATA);
  const sel = getChecked();
  div.innerHTML = '';
  names.filter(n => !filter || n.toLowerCase().includes(filter.toLowerCase()))
       .forEach((name) => {{
    const checked = sel.has(name) || (!sel.size && DEF_ITEMS.includes(name));
    const lbl = document.createElement('label');
    const col = COLORS[names.indexOf(name) % COLORS.length];
    lbl.style.borderLeftColor = col;
    lbl.style.borderLeftWidth = '3px';
    lbl.innerHTML = `<input type="checkbox" value="${{name}}" ${{checked?'checked':''}}
                      onchange="updateTrendChart()"> ${{name}}`;
    div.appendChild(lbl);
  }});
}}

function filterPicker() {{
  buildPicker(document.getElementById('trend-search').value);
}}

function getChecked() {{
  return new Set([...document.querySelectorAll('#trend-picker input:checked')].map(e=>e.value));
}}

function selectAll(state) {{
  document.querySelectorAll('#trend-picker input').forEach(cb => cb.checked = state);
  updateTrendChart();
}}

function selectTop10() {{
  document.querySelectorAll('#trend-picker input').forEach(cb => {{
    cb.checked = DEF_ITEMS.includes(cb.value);
  }});
  updateTrendChart();
}}

function updateTrendChart() {{
  const sel = [...getChecked()];
  const names = Object.keys(PRICE_DATA);
  const datasets = sel.map((name) => {{
    const col = COLORS[names.indexOf(name) % COLORS.length];
    return {{
      label: name,
      data: MONTHS.map(m => PRICE_DATA[name]?.[m] ?? null),
      borderColor: col,
      backgroundColor: col + '22',
      tension: 0.3,
      fill: false,
      spanGaps: true,
      pointRadius: 4,
    }};
  }});
  if (!trendChart) {{
    trendChart = new Chart(document.getElementById('trendChart'), {{
      type: 'line',
      plugins: [yearSepPlugin],
      data: {{ labels: MONTHS, datasets }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{ legend: {{ position: 'bottom', labels: {{ boxWidth: 12, font: {{ size: 11 }} }} }} }},
        scales: {{ y: {{ ticks: {{ callback: v => '€ ' + v.toFixed(2).replace('.',',') }} }} }}
      }}
    }});
  }} else {{
    trendChart.data.datasets = datasets;
    trendChart.update();
  }}
}}

function initTrends() {{
  window._trendInit = true;
  buildPicker();
  updateTrendChart();
}}

// ── Statistiken ──────────────────────────────────────────────────────────────
function initStats() {{
  window._statsInit = true;

  new Chart(document.getElementById('weekdayChart'), {{
    type: 'bar',
    data: {{
      labels: WEEKDAY_LABELS,
      datasets: [
        {{ label: 'Einkäufe', data: WEEKDAY_TRIPS, backgroundColor: '#457b9d99',
           borderColor: '#457b9d', borderWidth: 1.5, borderRadius: 4, yAxisID: 'y' }},
        {{ label: 'Ø Betrag (€)', data: WEEKDAY_AVG, type: 'line',
           borderColor: '#cc0000', backgroundColor: '#cc000022',
           tension: 0.3, yAxisID: 'y2', pointRadius: 5 }},
      ]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ position: 'bottom' }} }},
      scales: {{
        y:  {{ position: 'left',  ticks: {{ stepSize: 1 }} }},
        y2: {{ position: 'right', ticks: {{ callback: v => '€ ' + v.toFixed(0) }},
               grid: {{ drawOnChartArea: false }} }},
      }}
    }}
  }});

  new Chart(document.getElementById('bonusChart'), {{
    type: 'bar',
    data: {{
      labels: BONUS_MONTHS,
      datasets: [
        {{ label: 'Gesammelt (€)', data: BONUS_EARNED,
           backgroundColor: '#2a9d8f88', borderColor: '#2a9d8f',
           borderWidth: 1.5, borderRadius: 4, yAxisID: 'y' }},
        {{ label: 'Guthaben (€)', data: BONUS_BALANCE, type: 'line',
           borderColor: '#e9c46a', backgroundColor: '#e9c46a22',
           tension: 0.3, spanGaps: true, yAxisID: 'y2', pointRadius: 3 }},
      ]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ position: 'bottom' }} }},
      scales: {{
        y: {{
          position: 'left',
          title: {{ display: true, text: '← Gesammelt (€)', color: '#2a9d8f', font: {{ weight: '600' }} }},
          ticks: {{ color: '#2a9d8f', callback: v => '€ ' + v.toFixed(2).replace('.',',') }},
        }},
        y2: {{
          position: 'right',
          title: {{ display: true, text: 'Guthaben (€) →', color: '#c9a227', font: {{ weight: '600' }} }},
          ticks: {{ color: '#c9a227', callback: v => '€ ' + v.toFixed(2).replace('.',',') }},
          grid: {{ drawOnChartArea: false }},
        }},
      }}
    }}
  }});

  // Bonus-Rate pro Monat
  const avgPct = BONUS_PCT.filter(v => v != null);
  const overallAvg = avgPct.length ? (avgPct.reduce((a,b) => a+b,0)/avgPct.length).toFixed(2) : 0;
  new Chart(document.getElementById('bonusPctChart'), {{
    type: 'bar',
    data: {{
      labels: BONUS_MONTHS,
      datasets: [
        {{ label: 'Bonus-Rate (%)', data: BONUS_PCT,
           backgroundColor: ctx => {{
             const v = ctx.raw;
             if (v == null) return 'transparent';
             return v >= overallAvg ? '#2a9d8f88' : '#e9c46a88';
           }},
           borderColor: ctx => {{
             const v = ctx.raw;
             if (v == null) return 'transparent';
             return v >= overallAvg ? '#2a9d8f' : '#e9c46a';
           }},
           borderWidth: 1.5, borderRadius: 4 }},
      ]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{ callbacks: {{ label: ctx => ' ' + ctx.raw?.toFixed(2).replace('.',',') + ' %' }} }},
        annotation: {{}}
      }},
      scales: {{
        y: {{ ticks: {{ callback: v => v.toFixed(1) + ' %' }},
              suggestedMin: 0 }},
        x: {{ ticks: {{ maxRotation: 45 }} }}
      }}
    }}
  }});

  // Inflation-Tabelle initial befüllen
  renderInflation(INFLATION);
}}

let _infMode = 'all';
function filterInflation(mode, btn) {{
  _infMode = mode;
  document.querySelectorAll('.inf-active').forEach(b => b.classList.remove('inf-active'));
  btn.classList.add('inf-active');
  let data = INFLATION;
  if (mode === 'up')   data = INFLATION.filter(r => r.pct > 0);
  if (mode === 'down') data = INFLATION.filter(r => r.pct < 0).slice().reverse();
  renderInflation(data);
}}

function renderInflation(data) {{
  document.getElementById('inf-count').textContent = data.length + ' Artikel';
  document.getElementById('inf-body').innerHTML = data.map(r => {{
    const cls = r.pct > 0 ? 'pct-pos' : 'pct-neg';
    const sign = r.pct > 0 ? '+' : '';
    return `<tr>
      <td>${{r.n}}</td>
      <td class="num">${{r.fd}}</td><td class="num">${{eur(r.fp)}}</td>
      <td class="num">${{r.ld}}</td><td class="num">${{eur(r.lp)}}</td>
      <td class="num"><span class="${{cls}}">${{sign}}${{r.pct.toFixed(1).replace('.',',')}} %</span></td>
      <td class="num">${{r.cnt}}</td>
    </tr>`;
  }}).join('');
}}

// ── Alle Positionen ─────────────────────────────────────────────────────────
let posItems = ALL_ITEMS.slice();
let posSort  = {{ key: 'd', dir: -1 }};  // default: Datum absteigend

function initPositions() {{
  window._posInit = true;
  applyPositions();
}}

function sortPositions(th) {{
  const key = th.dataset.key;
  if (posSort.key === key) posSort.dir *= -1;
  else posSort = {{ key, dir: 1 }};
  document.querySelectorAll('#pos-table th').forEach(h => {{
    h.classList.remove('sort-asc','sort-desc');
  }});
  th.classList.add(posSort.dir === 1 ? 'sort-asc' : 'sort-desc');
  applyPositions();
}}

function applyPositions() {{
  const q   = (document.getElementById('pos-search')?.value || '').toLowerCase();
  const cat = document.getElementById('pos-cat')?.value || '';
  let items = ALL_ITEMS;
  if (q)   items = items.filter(r => r.n.toLowerCase().includes(q) || r.d.includes(q));
  if (cat) items = items.filter(r => r.cat === cat);

  const {{key, dir}} = posSort;
  items = [...items].sort((a, b) => {{
    let av = a[key], bv = b[key];
    if (typeof av === 'string') av = av.toLowerCase();
    if (typeof bv === 'string') bv = bv.toLowerCase();
    return av < bv ? -dir : av > bv ? dir : 0;
  }});

  const body = document.getElementById('pos-body');
  document.getElementById('items-count').textContent = items.length + ' Positionen';
  body.innerHTML = items.map(r => {{
    const pdfPath = 'pdfs/' + r.src.replace('.eml', '.pdf');
    return `<tr>
      <td class="num">${{isoDE(r.d)}}</td>
      <td>${{r.n}}</td>
      <td><span class="badge">${{r.cat}}</span></td>
      <td class="num">${{eur(r.p)}}</td>
      <td class="num">${{r.q > 1 ? eur(r.u) : '–'}}</td>
      <td class="num">${{r.q > 1 ? r.q + '×' : '–'}}</td>
      <td><a href="${{pdfPath}}" target="_blank" class="pdf-link">📄</a></td>
    </tr>`;
  }}).join('');
  alignHeaders('pos-table');
}}

function filterPositions() {{ applyPositions(); }}

// ── Alle Belege ─────────────────────────────────────────────────────────────
let recSort = {{ key: 'date', dir: -1 }};

function initReceipts() {{
  window._recInit = true;
  applyReceipts();
}}

function sortReceipts(th) {{
  const key = th.dataset.key;
  if (recSort.key === key) recSort.dir *= -1;
  else recSort = {{ key, dir: 1 }};
  document.querySelectorAll('#rec-table th').forEach(h =>
    h.classList.remove('sort-asc', 'sort-desc'));
  th.classList.add(recSort.dir === 1 ? 'sort-asc' : 'sort-desc');
  applyReceipts();
}}

function applyReceipts() {{
  const q = (document.getElementById('rec-search')?.value || '').toLowerCase();
  let list = ALL_RCPTS;
  if (q) list = list.filter(r =>
    r.date.includes(q) || r.bon.includes(q) || r.src.toLowerCase().includes(q));
  const {{key, dir}} = recSort;
  list = [...list].sort((a, b) => {{
    let av = a[key] ?? '', bv = b[key] ?? '';
    if (typeof av === 'string') av = av.toLowerCase();
    if (typeof bv === 'string') bv = bv.toLowerCase();
    return av < bv ? -dir : av > bv ? dir : 0;
  }});
  renderReceipts(list);
}}

function renderReceipts(list) {{
  const body = document.getElementById('rec-body');
  const rows = [];
  list.forEach((r, idx) => {{
    rows.push(`<tr class="expandable-row" onclick="toggleReceipt(${{idx}}, this)" data-idx="${{idx}}">
      <td style="width:1.5rem;text-align:center;color:#cc0000">▶</td>
      <td class="num">${{isoDE(r.date)}}</td>
      <td class="num">${{r.time}}</td>
      <td class="num"><strong>${{eur(r.total)}}</strong></td>
      <td class="num"><span class="badge">${{r.itemCnt}}</span></td>
      <td class="num" style="color:#2a9d8f;font-size:.85rem">${{r.bonus != null ? '+ ' + eur(r.bonus) : '–'}}</td>
      <td><a href="${{r.pdf}}" target="_blank" onclick="event.stopPropagation()" class="pdf-link">📄 PDF</a></td>
    </tr>`);
  }});
  body.innerHTML = rows.join('');
  body._list = list;
  alignHeaders('rec-table');
}}

function toggleReceipt(idx, row) {{
  // Remove existing expand row if open
  const next = row.nextElementSibling;
  if (next && next.classList.contains('expand-row')) {{
    next.remove();
    row.cells[0].textContent = '▶';
    return;
  }}
  // Close any other open expand rows
  document.querySelectorAll('.expand-row').forEach(r => r.remove());
  document.querySelectorAll('.expandable-row').forEach(r => {{ if(r.cells[0]) r.cells[0].textContent='▶'; }});

  const r = document.getElementById('rec-body')._list[idx];
  const lines = r.lines || [];
  const itemRows = lines.map(l => {{
    let einheit = '';
    if (l.q > 1)                          einheit = l.q + '× à ' + eur(l.u);
    else if (l.u && Math.abs(l.u - l.p) > 0.005) einheit = eur(l.u) + '/kg';
    return `<tr><td>${{l.n}}</td><td><span class="badge">${{l.cat}}</span></td>
      <td class="num">${{eur(l.p)}}</td>
      <td class="num" style="color:#888">${{einheit}}</td></tr>`;
  }}).join('');

  const expand = document.createElement('tr');
  expand.className = 'expand-row';
  expand.innerHTML = `<td colspan="7">
    <table style="width:100%">
      <thead><tr>
        <th>Artikel</th><th>Kategorie</th>
        <th class="num">Preis</th><th class="num">Menge / Kilopreis</th>
      </tr></thead>
      <tbody>${{itemRows}}</tbody>
    </table>
  </td>`;
  row.after(expand);
  row.cells[0].textContent = '▼';
}}

function filterReceipts() {{ applyReceipts(); }}
</script>
</body>
</html>"""

    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"\nReport gespeichert: {REPORT_PATH}")


# ── Hauptprogramm ──────────────────────────────────────────────────────────────

def main():
    eml_files = sorted(IMPORT_DIR.glob("Dein REWE eBon*.eml"))
    if not eml_files:
        print("Keine EML-Dateien gefunden.")
        sys.exit(1)

    print(f"Gefunden: {len(eml_files)} EML-Dateien")

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    # Direkte PDFs aus import/ ebenfalls einsammeln
    pdf_files = sorted(IMPORT_DIR.glob("*.pdf"))

    # Bereits verarbeitete Dateien überspringen
    done = {row[0] for row in conn.execute("SELECT filename FROM processed_files")}
    new_emls = [p for p in eml_files if p.name not in done]
    new_pdfs = [p for p in pdf_files if p.name not in done]
    new_files = new_emls + new_pdfs

    # PDFs immer aktuell halten (fehlende extrahieren + direkte kopieren)
    print("Extrahiere/kopiere PDFs…")
    extract_all_pdfs()
    print("Bonus-Daten ergänzen…")
    backfill_bonus(conn)

    if not new_files:
        print("Keine neuen Belege gefunden. Erstelle Report aus vorhandenen Daten...")
        generate_report(conn)
        total = conn.execute("SELECT COUNT(*), ROUND(SUM(total),2) FROM receipts").fetchone()
        items = conn.execute("SELECT COUNT(*) FROM items").fetchone()
        print(f"Datenbank: {total[0]} Belege, {items[0]} Artikel, Gesamt: € {total[1]}")
        conn.close()
        print(f"\nÖffne Report: open '{REPORT_PATH}'")
        return

    print(f"Neu zu verarbeiten: {len(new_files)} (EML: {len(new_emls)}, PDF: {len(new_pdfs)}) | Bereits in DB: {len(done)}")

    ok, fail = 0, 0
    for i, path in enumerate(new_files, 1):
        sys.stdout.write(f"\r  Verarbeite {i}/{len(new_files)}: {path.name[:50]:<50}")
        sys.stdout.flush()
        is_pdf = path.suffix.lower() == '.pdf'
        if (process_pdf_direct if is_pdf else process_eml)(path, conn):
            ok += 1
            try:
                path.unlink()   # nach erfolgreicher Verarbeitung aus import/ löschen
            except Exception:
                pass
        else:
            fail += 1

    print(f"\n\nErgebnis: {ok} neu, {fail} fehlgeschlagen")

    # Statistik ausgeben
    total = conn.execute("SELECT COUNT(*), ROUND(SUM(total),2) FROM receipts").fetchone()
    items = conn.execute("SELECT COUNT(*) FROM items").fetchone()
    print(f"Datenbank: {total[0]} Belege, {items[0]} Artikel, Gesamt: € {total[1]}")

    generate_report(conn)
    conn.close()

    print(f"\nÖffne Report: open '{REPORT_PATH}'")


if __name__ == '__main__':
    main()
