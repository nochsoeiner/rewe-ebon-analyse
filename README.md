# REWE eBon Analyse

Lokales Analyse-Tool für REWE eBon-Kassenbons (EML mit PDF-Anhang).
Erstellt einen interaktiven HTML-Bericht aus den eigenen Einkaufsdaten.

## Features

- 📊 **Dashboard** – Monatsausgaben, Jahresübersicht, Top-Artikel, Kategorien
- 📈 **Preisentwicklung** – Preishistorie einzelner Artikel über die Zeit
- 🔍 **Statistiken** – Wochentag-Analyse, Inflations-Tracker, Bonus-Guthaben, Bonus-Rate pro Monat (% des Umsatzes)
- 🗂 **Alle Positionen** – Suchbar & sortierbar nach allen Spalten
- 🧾 **Alle Belege** – Aufklappbar mit Detailansicht, direkter PDF-Link

## Voraussetzungen

```bash
pip install pdfplumber
```

Python 3.9+ wird benötigt.

## Nutzung

### Einfachster Weg: Doppelklick
→ `Auswertung starten.command` im Finder doppelklicken

### Per Terminal
```bash
cd Rewe/
python3 rewe_analyze.py
```

### Neue Kassenbons hinzufügen

**Option A – EML (aus Apple Mail):**
1. eBon-Mail in Apple Mail öffnen
2. *Ablage → Als Datei sichern…* → `.eml`-Datei in den `import/`-Ordner legen
3. `Auswertung starten.command` doppelklicken

**Option B – Direkte PDF:**
1. PDF-Datei direkt in den `import/`-Ordner legen
2. `Auswertung starten.command` doppelklicken

Das Skript erkennt automatisch neue EML- und PDF-Dateien, verarbeitet nur diese
und **löscht sie danach automatisch** aus dem `import/`-Ordner.

## Ordnerstruktur

```
Rewe/
├── import/                  ← EML, oder PDF-Dateien hier ablegen
├── pdfs/                    ← auto-extrahierte PDFs (wird auto-erstellt)
├── rewe_analyze.py          ← Hauptskript
├── rewe_ebons.db            ← Datenbank (wird auto-erstellt)
├── rewe_report.html         ← Bericht (wird auto-erstellt)
└── Auswertung starten.command
```

> **Hinweis:** `import/`, `pdfs/`, `rewe_ebons.db` und `rewe_report.html`
> enthalten persönliche Daten und sind in `.gitignore` ausgeschlossen.
