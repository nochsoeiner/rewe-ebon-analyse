# REWE eBon Analyse

Lokales Analyse-Tool für REWE eBon-Kassenbons (EML mit PDF-Anhang).
Erstellt einen interaktiven HTML-Bericht aus den eigenen Einkaufsdaten.

## Features

- 📊 **Dashboard** – Monatsausgaben, Jahresübersicht, Top-Artikel, Kategorien
- 📈 **Preisentwicklung** – Preishistorie einzelner Artikel über die Zeit
- 🔍 **Statistiken** – Wochentag-Analyse, Inflations-Tracker, Bonus-Guthaben
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
1. eBon-Mail in Apple Mail öffnen
2. *Ablage → Als Datei sichern…* → in den `import/`-Ordner speichern
3. `Auswertung starten.command` doppelklicken

Das Skript erkennt automatisch neue EML-Dateien und verarbeitet nur diese.

## Ordnerstruktur

```
Rewe/
├── import/                  ← EML-Dateien hier ablegen
├── pdfs/                    ← auto-extrahierte PDFs (wird auto-erstellt)
├── rewe_analyze.py          ← Hauptskript
├── rewe_ebons.db            ← Datenbank (wird auto-erstellt)
├── rewe_report.html         ← Bericht (wird auto-erstellt)
└── Auswertung starten.command
```

> **Hinweis:** `import/`, `pdfs/`, `rewe_ebons.db` und `rewe_report.html`
> enthalten persönliche Daten und sind in `.gitignore` ausgeschlossen.
