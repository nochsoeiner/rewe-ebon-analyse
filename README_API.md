# Lokale REWE-API

`rewe_api.py` stellt die SQLite-Daten der REWE-eBon-App ausschließlich lokal und nur lesend für das Haushalts-Dashboard bereit.

Der vorhandene Server auf Port 7331 wurde nicht wiederverwendet: Er gehört zur interaktiven REWE-Auswertung und besitzt bewusst schreibende Endpunkte für Gruppen und Kategorien. Die neue API ist deshalb als eigener, kleiner Read-only-Dienst getrennt. Sie importiert keine Mails, startet Mail.app nicht und enthält keinerlei Upload-, SSH- oder SCP-Funktion.

## Start

Direkt aus dem Quellordner:

```sh
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
  "/Users/marc/Server/Lieferanten-Apps/Rewe/rewe_api.py"
```

Oder mit der bereitgestellten Laufzeitkopie:

```sh
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
  "/Users/marc/Library/Application Support/Rewe/rewe_api.py"
```

Standardmäßig lauscht die API nur auf `127.0.0.1:7332`. Die Bind-Adresse ist absichtlich nicht konfigurierbar, damit der Dienst niemals versehentlich auf `0.0.0.0` veröffentlicht wird. Beenden mit `Ctrl-C`.

Der Port und die erlaubten Browser-Origins sind über Umgebungsvariablen konfigurierbar:

```sh
REWE_API_PORT=7332 \
REWE_API_ALLOWED_ORIGINS="http://127.0.0.1:4173,http://localhost:4173,http://127.0.0.1:3000,http://localhost:3000" \
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
  "/Users/marc/Library/Application Support/Rewe/rewe_api.py"
```

Nur explizite Origins auf `localhost`, `127.0.0.1` oder `::1` werden akzeptiert. Eine Wildcard oder eine nicht lokale Origin führt beim Start zu einem Fehler.

## Endpunkte

- `GET /api/v1/rewe/status` – Healthcheck, DB-Zeitstempel, Gesamtzahl aller Bons und jüngster Bon.
- `GET /api/v1/rewe` – Datenstruktur für das Dashboard. Wie die bisherige `rewe-data.json` enthält sie das aktuelle Kalenderjahr und die kompatiblen Felder `meta.pdfCount`, `meta.periodStart`, `meta.periodEnd` und `meta.preparedAt`.
- `GET /api/v1/rewe/receipts/:id` – ein Bon samt Positionen.
- `GET /api/v1/rewe/receipts/:id/pdf` – das zu dieser Bon-ID gehörende PDF.

Alle Antworten enthalten `Cache-Control: no-store`. JSON und PDF werden bei jedem Aufruf aus der aktuellen Datenbank beziehungsweise dem aktuellen PDF-Ordner ermittelt. Es ist kein Neustart nach einem Mail-Import nötig.

Healthcheck:

```sh
curl --fail --show-error http://127.0.0.1:7332/api/v1/rewe/status
```

Dashboard-Daten:

```sh
curl --fail --show-error http://127.0.0.1:7332/api/v1/rewe
```

Der Browser des Haushalts-Dashboards kann die Daten beispielsweise von `http://127.0.0.1:7332/api/v1/rewe` laden. Die `pdfUrl`-Werte sind wie angefordert API-relative Pfade; das Dashboard muss sie gegen dieselbe API-Basis auflösen oder seinen lokalen Dev-Server als Proxy konfigurieren.

## Datenbank- und PDF-Sicherheit

- SQLite wird über `mode=ro` und zusätzlich mit `PRAGMA query_only=ON` geöffnet.
- Jede Anfrage verwendet eine neue Read-only-Verbindung und sieht deshalb neue Bons ohne Serverneustart.
- Kurzzeitige `locked`-/`busy`-Zustände werden mit begrenzten Wiederholungen abgefangen.
- IDs werden als positive Ganzzahlen aus einer festen Route gelesen und als SQL-Parameter gebunden.
- PDF-Pfade werden nie aus URL-Eingaben gebaut. Die API liest zuerst die Bon-ID aus SQLite und sucht das PDF nur im fest konfigurierten PDF-Ordner.
- API-Fehler enthalten keine internen Dateipfade.

## Tests

Die Tests arbeiten ausschließlich mit einer temporären Datenbank und verändern die echte REWE-Datenbank nicht:

```sh
cd "/Users/marc/Server/Lieferanten-Apps/Rewe"
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 -m unittest -v tests.test_rewe_api
```

## Optionaler LaunchAgent

Unter `launchd/com.marc.rewe-api.plist.example` liegt eine Vorlage für einen automatischen Start nach der Anmeldung. Sie ist absichtlich nur eine Vorlage und wird nicht automatisch nach `~/Library/LaunchAgents` kopiert oder mit `launchctl` aktiviert.
