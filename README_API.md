# Lokale REWE-API

`rewe_api.py` stellt die SQLite-Daten der REWE-eBon-App lokal und nur lesend für das Haushalts-Dashboard bereit. Die Marktpreisprüfung ist eine gesonderte, vom Nutzer gestartete Netzabfrage.

Im regulären Betrieb bindet der gemeinsame Haushalt-Server die REWE-API auf Port 4173 ein. Der optionale Server auf Port 7331 gehört zur interaktiven REWE-Auswertung und besitzt schreibende Endpunkte für Gruppen und Kategorien. Ein separater API-Start auf Port 7332 bleibt für Entwicklung und Tests möglich. Die API selbst importiert keine Mails, startet Mail.app nicht und enthält keinerlei Upload-, SSH- oder SCP-Funktion.

## Start

Direkt aus dem Quellordner:

```sh
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
  "/Users/marc/Server/Haushalt 4173/lieferanten/REWE/rewe_api.py"
```

Im aktuellen Haushalt-Setup bindet `server.py` die REWE-API direkt unter `http://127.0.0.1:4173/api/v1/rewe` ein. `./install.sh` richtet die stündliche Berichtserstellung und die bestehende Online-Veröffentlichung ein. Die Daten liegen in `~/Library/Application Support/Rewe` (`REWE_DATA_DIR`). Der separate Start auf Port 7332 bleibt für Entwicklung und Tests möglich.

Standardmäßig lauscht die API nur auf `127.0.0.1:7332`. Die Bind-Adresse ist absichtlich nicht konfigurierbar, damit der Dienst niemals versehentlich auf `0.0.0.0` veröffentlicht wird. Beenden mit `Ctrl-C`.

Der Port und die erlaubten Browser-Origins sind über Umgebungsvariablen konfigurierbar:

```sh
REWE_API_PORT=7332 \
REWE_API_ALLOWED_ORIGINS="http://127.0.0.1:4173,http://localhost:4173,http://127.0.0.1:3000,http://localhost:3000" \
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 \
  "/Users/marc/Server/Haushalt 4173/lieferanten/REWE/rewe_api.py"
```

Nur explizite Origins auf `localhost`, `127.0.0.1` oder `::1` werden akzeptiert. Eine Wildcard oder eine nicht lokale Origin führt beim Start zu einem Fehler.

## Endpunkte

- `GET /api/v1/rewe/status` – Healthcheck, DB-Zeitstempel, Gesamtzahl aller Bons und jüngster Bon.
- `GET /api/v1/rewe` – Datenstruktur für das Dashboard. Wie die bisherige `rewe-data.json` enthält sie das aktuelle Kalenderjahr und die kompatiblen Felder `meta.pdfCount`, `meta.periodStart`, `meta.periodEnd` und `meta.preparedAt`.
- `GET /api/v1/rewe/receipts/:id` – ein Bon samt Positionen.
- `GET /api/v1/rewe/receipts/:id/pdf` – das zu dieser Bon-ID gehörende PDF.
- `GET /api/v1/rewe/shop-items?channel=market|online` – liefert alle unterschiedlichen gekauften Artikelnamen des gewählten Kanals samt Kaufanzahl und letztem Preis, ohne REWE zu kontaktieren. `market` beschränkt eBons auf die Kassen-Marktkennung 5775 des Markts Holzhäuserstr. 110; `online` nutzt alle Online-Rechnungen.
- `POST /api/v1/rewe/shop-check` – prüft eine Seite von höchstens 25 Artikeln. Beispiel: `{"channel":"market","offset":0,"limit":25,"known":{}}`. `market` nutzt den Markt Holzhäuserstr. 110 (Shop-Markt-ID 4040430, Abholsortiment); `online` den Lieferservice für PLZ 04299 (Shop-Markt-ID 4600006). Der Browser durchläuft nach Klick alle Seiten und zeigt den Fortschritt. Erst der jeweilige Klick sendet die betreffenden Artikelnamen an REWE. Der Request benötigt eine ausdrücklich erlaubte lokale Origin und JSON. Die Anfragen werden zeitlich verteilt; auf HTTP 429 folgen begrenzte Wiederholungen. Bei einer längeren Sperre liefert die API bereits geprüfte Artikel mit `paused: true` und passendem `nextOffset`, sodass der Nutzer im selben geöffneten Bericht fortsetzen kann.

Die Marktpreise und Verfügbarkeitsangaben stammen aus dem **Abholsortiment** des gewählten Markts und sind kein Nachweis für den Regalbestand. Die Onlineangaben stammen aus dem **Lieferservice**. Ein erstmalig nicht gefundener oder mehrdeutiger Artikel wird als „nicht sicher zugeordnet“ angezeigt; „nicht verfügbar“ gilt nur für eine zuvor eindeutig zugeordnete Produkt-ID desselben Einkaufskanals. Die offiziellen REWE-Angebotsseiten sind aus dem Bericht verlinkt. Die manuelle Einzelprüfung funktioniert nur in der lokalen Haushalts-App; die Online-Fassung zeigt den zuletzt erstellten Angebotsstand ohne eigene REWE-Anfragen.

`python3 rewe_offer_refresh.py` lädt die rabattierten Shop-Produkte für beide Kanäle seitenweise (`attribute=discounted`) und gleicht sie lokal mit allen eBons beziehungsweise Online-Rechnungen ab. Die REWE-Anfragen enthalten dabei keine gekauften Artikelnamen. Erst nach vollständigem Abruf beider Angebotslisten wird `rewe_offer_snapshot.json` atomar ersetzt und der HTML-Bericht neu erstellt. Bei fehlgeschlagenem Abruf bleibt der letzte vollständige Snapshot erhalten und wird auch nach 30 Stunden weiter im Bericht eingebettet. Die Anzeige prüft das Gültigkeitsdatum jedes Angebots in der Zeitzone Europe/Berlin; der von REWE angegebene Endtag ist einschließlich gültig. Noch gültige Angebote bleiben sichtbar. Abgelaufene Treffer erscheinen unter „Zuletzt erfasste Angebote“ mit dem damaligen Preis. Angebote ohne auswertbares Enddatum werden nach 30 Stunden dort als „Gültigkeit nicht bestätigt“ angezeigt. Die Prüfung erfolgt auch beim Öffnen eines älteren veröffentlichten Berichts und jede Minute auf einer geöffneten Seite. Nicht angebotene Produkte bleiben bezüglich Verfügbarkeit ungeprüft; die Angebotsliste kann fehlende Artikel nicht nachweisen. Eine bestehende Report-WatchPath-Veröffentlichung übernimmt den neu erstellten Bericht.

## Wöchentlicher Angebotsabruf und mobile Darstellung

Der macOS-LaunchAgent `com.marc.rewe-offers` startet `rewe_offer_refresh.py`
direkt mit Python, sonntags um **18:00 Uhr lokaler Mac-Zeit** (im eingerichteten
Betrieb Europe/Berlin). Er benötigt weder eine laufende App noch einen Browser.
`install.sh` richtet ihn mit ein; `python3 scripts/install-offer-job.py` installiert
nur diesen Job, ohne die bestehenden Veröffentlichungsjobs neu zu laden.
Die Konfiguration wird über `plistlib` mit absoluten Code-, Python- und Datenpfaden
erzeugt. Die systemeigene Kalenderplanung übernimmt den wöchentlichen Start.
Der Mac muss eingeschaltet und der Benutzer angemeldet sein.

Status und Logs:

```bash
launchctl print "gui/$(id -u)/com.marc.rewe-offers"
tail -n 30 ~/Library/Logs/rewe-offers.log
tail -n 30 ~/Library/Logs/rewe-offers-error.log
```

Die gemeinsame Dienstüberwachung prüft, ob der LaunchAgent geladen ist, und lädt
einen fehlenden Job nach. Die stündliche Berichtserstellung und die
Veröffentlichung sind eigene Abläufe; der Angebotsjob erzeugt den Bericht erst
nach dem Katalogabruf neu. Gültigkeitsdaten und historische Treffer werden wie
oben beschrieben ausgewertet.

Der Bericht zeigt Angebote mit Produktbild, aktuellem und regulärem Preis,
Rabatt, Gültigkeit, letztem eigenen Kaufpreis und Kaufanzahl. Eine mobile
Beispielansicht steht in der [README](README.md#neu-angebote-passend-zu-den-eigenen-einkäufen).
Mehrere Bon-Bezeichnungen derselben Produkt-ID werden je Kanal bei gleichem
Status, Preis und Gültigkeitsende zu einer Karte zusammengefasst. Kaufzahlen
werden addiert; `lastPurchaseDate` und `lastPurchaseId` bestimmen den jüngsten
Kaufpreis gemäß der bestehenden Datums-/Positionsreihenfolge. Die unveränderten
Bon-Bezeichnungen bleiben einzeln in der Artikelliste erhalten. Beim Erzeugen des
Berichts wird ihre Kaufhistorie aus der lokalen Datenbank ergänzt, ohne den
Zeitpunkt des letzten Katalogabrufs zu verändern. Fehlt bei einem alten Stand
die zeitliche Zuordnung, zeigt die Karte bei unterschiedlichen Kaufpreisen eine
Spanne statt eines geratenen letzten Preises. Unterschiedliche Produkt-IDs oder
Angebotskonditionen werden nicht zusammengeführt.
Bis 600 px bleibt die Navigation unten am Bildschirmrand. Beim Tabwechsel wird
die Dokumentposition sofort nach oben gesetzt; Tabellen besitzen eigene
Scrollbereiche und verbreitern die Seite nicht.

## Frische Antworten

Alle Antworten enthalten `Cache-Control: no-store`. JSON und PDF werden bei jedem Aufruf aus der aktuellen Datenbank beziehungsweise dem aktuellen PDF-Ordner ermittelt. Es ist kein Neustart nach einem Mail-Import nötig.

Healthcheck:

```sh
curl --fail --show-error http://127.0.0.1:7332/api/v1/rewe/status
```

Dashboard-Daten:

```sh
curl --fail --show-error http://127.0.0.1:7332/api/v1/rewe
```

Der Browser des Haushalts-Dashboards nutzt die API unter derselben Origin auf Port 4173. Die `pdfUrl`-Werte sind API-relative Pfade und werden ebenfalls über diesen Server ausgeliefert.

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
cd "/Users/marc/Server/Haushalt 4173/lieferanten/REWE"
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 -m unittest -v tests.test_rewe_api
```

## Optionaler LaunchAgent

Unter `launchd/com.marc.rewe-api.plist.example` liegt eine Vorlage für einen automatischen Start nach der Anmeldung. Sie ist absichtlich nur eine Vorlage und wird nicht automatisch nach `~/Library/LaunchAgents` kopiert oder mit `launchctl` aktiviert.
