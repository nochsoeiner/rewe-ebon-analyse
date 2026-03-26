# REWE eBon Analyse

Lokales Analyse-Tool für REWE eBon-Kassenbons (EML mit PDF-Anhang).
Erstellt einen interaktiven HTML-Bericht aus den eigenen Einkaufsdaten.

## Features

- 📊 **Dashboard** – Monatsausgaben, Jahresübersicht, Top-30-Artikel (nach Häufigkeit & Ausgaben), Kategorien, Warenkorbanalyse, Saisonale Muster, Monatsforecast
- 📈 **Preisentwicklung** – Preishistorie einzelner Artikel; Rangliste der größten Preisschwankungen und stabilsten Preise (je mit Min/Max/Käufe-Angabe)
- 🔍 **Statistiken** – Wochentag-Analyse, Inflations-Tracker, Bonus-Guthaben, Bonus-Rate, Preis-Alarm (letzter Kauf > 10 % über Durchschnitt)
- 🗂 **Alle Positionen** – Suchbar & sortierbar; zeigt €/kg für Gewichtsartikel und Menge in Gramm
- 🧾 **Alle Belege** – Aufklappbar mit Detailansicht, direkter PDF-Link
- 🥦 **Verbrauch** – Jahresverbrauch in kg und Stückzahlen, „Hält ø X Tage"-Spalte, Wiederbestellungs-Prognose mit sortierbaren Spalten
- 🏷 **Gruppen** – Ähnliche Artikel zusammenfassen (z. B. alle Bananen-Varianten), direkt im Browser editierbar; Gruppierungen wirken auf Dashboard, Verbrauch und Warenkorbanalyse
- 🤖 **Automatischer Mail-Import** – Neuer eBon in Apple Mail → EML wird automatisch exportiert und verarbeitet (via launchd + AppleScript)

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
python3 rewe_analyze.py          # Auswertung + Report generieren
python3 rewe_analyze.py --serve  # wie oben + Browser öffnen + Gruppen-Server starten
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
├── import/                  ← EML- oder PDF-Dateien hier ablegen
├── pdfs/                    ← auto-extrahierte PDFs (wird auto-erstellt)
├── rewe_analyze.py          ← Hauptskript
├── rewe_ebons.db            ← Datenbank (wird auto-erstellt)
├── rewe_report.html         ← Bericht (wird auto-erstellt)
├── groups.json              ← Artikel-Gruppen (wird beim Speichern im Browser erstellt)
├── export_rewe_mail.sh      ← Mail-Export-Skript (für automatischen Import)
└── Auswertung starten.command
```

> **Hinweis:** `import/`, `pdfs/`, `rewe_ebons.db` und `rewe_report.html`
> enthalten persönliche Daten und sind in `.gitignore` ausgeschlossen.

---

*Dieses Projekt steht in keiner Verbindung zur REWE Group. „REWE" und „eBon" sind Marken der REWE Group.*
