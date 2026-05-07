# REWE eBon Analyse

Lokales Analyse-Tool für REWE eBon-Kassenbons (EML mit PDF-Anhang).
Erstellt einen interaktiven HTML-Bericht aus den eigenen Einkaufsdaten.

<img width="661" height="887" alt="Bildschirmfoto 2026-03-27 um 14 51 14" src="https://github.com/user-attachments/assets/7dbbb74f-a8b4-4861-9823-aa0f78679b72" />


<img width="617" height="899" alt="Bildschirmfoto 2026-03-27 um 14 50 33" src="https://github.com/user-attachments/assets/22e96a17-1b9f-49d3-992a-847bb0cbabff" />


## Version 1.0

Diese Version bringt zahlreiche neue Funktionen und einen aufgeräumten Tab-Aufbau:

- 🛒 **Einkaufszettel** als eigener Reiter — Karten mit Kategorie-Emoji, Vorschläge unten, gewählte Artikel oben (klickbar nach oben/unten), eigene Einträge per "Ich brauche…", Liste leeren, Kopieren, Drucken
- 📅 **Haltbarkeit & Wochenverbrauch** — wie lange hält 1 Einheit, was geht pro Woche durch (Stück + kg vereint, Gruppen aufklappbar)
- 🏷 **Kategorie pro Artikel manuell anpassen** — Klick auf Badge in "Alle Positionen", Override gilt für alle gleichlautenden Artikel (gespeichert in `categories_override.json`)
- 🧹 **Artikelnamen-Bereinigung** — REWE-Markt-GmbH-Footer und zusammengeklebte Gewichtsartikel werden automatisch gesäubert
- 📊 **Aufgeräumter Tab-Aufbau**: Statistiken-Reiter aufgelöst — Wochentage und Bonus jetzt im Dashboard, Preis-Alarm und Inflation in Preisentwicklung
- 🔢 **Deutsche Tausendertrennung** in allen Charts und Tabellen
- 🌱 **Saisonale Muster normalisiert** — Werte über mehrere Jahre werden gemittelt, sodass Saisons mit doppelter Datenabdeckung nicht überrepräsentiert sind
- 🛍 **REWE Shop (Lieferservice) Import** zusätzlich zu eBon-Mails

## Features

- 📊 **Dashboard** – Monatsausgaben, Jahresübersicht, Top-30-Artikel (Häufigkeit & Ausgaben), Kategorien, Wochentag-Analyse, Bonus-Guthaben & Bonus-Rate, Saisonale Muster (normalisiert), Monatsforecast
- 📈 **Preisentwicklung** – Preishistorie einzelner Artikel, Größte Preisschwankung & Stabilste Preise mit Min/Max/Letzt/Käufe-Angabe, Kürzlich gestiegen, Preis-Alarm, Inflations-Tabelle
- 🛒 **Einkaufszettel** – Auto-Vorschläge basierend auf Wochenverbrauch & Kaufintervall, Karten-Layout, eigene Einträge, Kopieren/Drucken
- 🥦 **Verbrauch** – Haltbarkeit & Wochenverbrauch (Stück + kg vereint), Jahresverbrauch in kg und Stückzahlen, Wiederbestellungs-Prognose, Gruppen aufklappbar
- 🗂 **Alle Positionen** – Suchbar & sortierbar; Kategorie pro Artikel klickbar änderbar; €/kg für Gewichtsartikel; Menge in Gramm
- 🧾 **Alle Belege** – Aufklappbar mit Detailansicht, direkter PDF-Link
- 🏷 **Artikel-Gruppen** – Ähnliche Artikel zusammenfassen (z. B. alle Bananen-Varianten), direkt im Browser editierbar; Gruppierungen wirken auf Dashboard, Verbrauch und Warenkorbanalyse
- 🤖 **Automatischer Mail-Import** – Neue eBon in Apple Mail → EML wird automatisch exportiert und verarbeitet (via launchd + AppleScript)

## Voraussetzungen

```bash
pip install pdfplumber
```

Python 3.9+ wird benötigt.

## Nutzung

### Einfachster Weg: Doppelklick
→ `Auswertung starten.command` im Finder doppelklicken

Startet die Auswertung, öffnet den Report im Browser **und** den lokalen Server,
damit Gruppen- und Kategorie-Änderungen aus dem Browser heraus persistiert werden können.

### Per Terminal
```bash
cd Rewe/
python3 rewe_analyze.py          # Auswertung + Report generieren
python3 rewe_analyze.py --serve  # wie oben + Browser öffnen + Server starten
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
├── import/                       ← EML- oder PDF-Dateien hier ablegen
├── pdfs/                         ← auto-extrahierte PDFs (wird auto-erstellt)
├── rewe_analyze.py               ← Hauptskript
├── rewe_ebons.db                 ← Datenbank (wird auto-erstellt)
├── rewe_report.html              ← Bericht (wird auto-erstellt)
├── groups.json                   ← Artikel-Gruppen (wird im Browser gespeichert)
├── categories_override.json      ← Kategorie-Overrides (wird im Browser gespeichert)
├── export_rewe_mail.sh           ← Mail-Export-Skript (für automatischen Import)
└── Auswertung starten.command
```

> **Hinweis:** `import/`, `pdfs/`, `rewe_ebons.db`, `rewe_report.html`,
> `groups.json` und `categories_override.json` enthalten persönliche Daten
> und sind in `.gitignore` ausgeschlossen.

## Datenmodell

- `rewe_ebons.db` – SQLite mit zwei Tabellen: `receipts` (Kassenbons) und `items` (Positionen)
- `groups.json` – Mapping `Gruppenname → [Artikelname, …]` für Zusammenfassungen
- `categories_override.json` – Mapping `Artikelname → Kategorie` für manuelle Korrekturen

Beide JSON-Dateien werden vom lokalen Server bei Änderungen im Browser geschrieben
(`--serve`-Modus erforderlich).

---

*Dieses Projekt steht in keiner Verbindung zur REWE Group. „REWE" und „eBon" sind Marken der REWE Group.*
