# Rewe Mail Export – Einrichtung

## Dateien
- `export_rewe_mails.applescript` → Das eigentliche Exportskript
- `com.marc.rewe-mail-export.plist` → Launchd-Agent (Ausführung alle 30 Minuten)

---

## Installation (einmalig, im Terminal)

### 1. Skript-Ordner anlegen und Skript ablegen
```bash
mkdir -p ~/Scripts
cp ~/Downloads/export_rewe_mails.applescript ~/Scripts/
```

### 2. Launchd-Agent installieren
```bash
cp ~/Downloads/com.marc.rewe-mail-export.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.marc.rewe-mail-export.plist
```

### 3. Sofort testen (ohne zu warten)
```bash
launchctl start com.marc.rewe-mail-export
```

Danach im Zielordner prüfen:
```
~/Library/Mobile Documents/com~apple~CloudDocs/Claude/Rewe/import/
```

---

## Logs prüfen
```bash
# Was wurde exportiert?
cat ~/Library/Logs/rewe-mail-export.log

# Fehler?
cat ~/Library/Logs/rewe-mail-export-error.log

# Kompakt-Log im iCloud-Ordner
cat ~/Library/Mobile\ Documents/com~apple~CloudDocs/Claude/Rewe/import/.export_log.txt
```

---

## Wichtig: Mail.app-Zugriffsrechte

Beim ersten Start fragt macOS, ob `osascript` auf Mail.app zugreifen darf.
→ **"OK" / "Erlauben" klicken.**

Falls die Abfrage nicht erscheint oder der Export fehlschlägt:
**Systemeinstellungen → Datenschutz & Sicherheit → Automatisierung**
→ Dort sicherstellen, dass `osascript` (oder Terminal) Zugriff auf Mail hat.

---

## Agent deaktivieren (falls nötig)
```bash
launchctl unload ~/Library/LaunchAgents/com.marc.rewe-mail-export.plist
```

## Verhalten
- Läuft alle 30 Minuten und beim Mac-Start automatisch
- Prüft eBons im Mail-Ordner `Rewe` und Lieferdienst-Rechnungen mit Betreff `Rechnung zu B-` in den Posteingängen
- Exportiert jede Mail nur **einmal** (prüft, ob .eml-Datei bereits existiert)
- Dateiname: `YYYYMMDD_HHMMSS_<messageID>.eml`
- Schreibt ein kompaktes Log in den iCloud-Importordner (`.export_log.txt`)
