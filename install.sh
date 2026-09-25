#!/bin/bash
# Installiert/aktualisiert die REWE-Dienste:
#   Code läuft direkt aus diesem Ordner (Repo), Daten in ~/Library/Application Support/Rewe (REWE_DATA_DIR)
#   com.marc.rewe-api          Read-only-API → 127.0.0.1:7332
#   com.marc.rewe-web-update   stündlich: Online-Änderungen holen, Bericht erzeugen, veröffentlichen
#   com.marc.rewe-web-publish  bei neuem Bericht: Online-Fassung aktualisieren
# Neue eBons holt der gemeinsame Mail-Export (Regeln rewe-ebon/rewe-shop) und stößt rewe-web-update an.
# Mehrfach ausführbar – schreibt die LaunchAgents und startet die Dienste neu, Daten bleiben erhalten.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
RT="$HOME/Library/Application Support/Rewe"
AGENTS="$HOME/Library/LaunchAgents"
LOGS="$HOME/Library/Logs"
PY=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3
DOMAIN="gui/$(id -u)"
LABELS=(com.marc.rewe-api com.marc.rewe-web-update com.marc.rewe-web-publish)

mkdir -p "$RT/import" "$RT/pdfs" "$RT/web/pdfs" "$RT/web/last" "$AGENTS"
chmod +x "$SRC/scripts/web-update.sh" "$SRC/scripts/web-publish.sh"

plist() { # label, program-args-xml, extra-xml, log-name
cat > "$AGENTS/$1.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$1</string>
    <key>ProgramArguments</key>
    <array>
$2
    </array>
    <key>WorkingDirectory</key>
    <string>$RT</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>REWE_DATA_DIR</key>
        <string>$RT</string>
        <key>REWE_API_PORT</key>
        <string>7332</string>
        <key>REWE_API_ALLOWED_ORIGINS</key>
        <string>http://127.0.0.1:4173,http://localhost:4173,http://127.0.0.1:3000,http://localhost:3000</string>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
    </dict>
$3
    <key>ProcessType</key>
    <string>Background</string>
    <key>StandardOutPath</key>
    <string>$LOGS/$4.log</string>
    <key>StandardErrorPath</key>
    <string>$LOGS/$4-error.log</string>
</dict>
</plist>
PLIST
}

plist com.marc.rewe-api "        <string>$PY</string>
        <string>$SRC/rewe_api.py</string>" '    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>' rewe-api

# Das Skript schreibt selbst nach ~/Library/Logs/rewe-web-update.log (vom Watchdog überwacht)
plist com.marc.rewe-web-update "        <string>/bin/bash</string>
        <string>$SRC/scripts/web-update.sh</string>" '    <key>StartInterval</key>
    <integer>3600</integer>' rewe-web-update.launchd

plist com.marc.rewe-web-publish "        <string>/bin/bash</string>
        <string>$SRC/scripts/web-publish.sh</string>" "    <key>WatchPaths</key>
    <array>
        <string>$RT/rewe_report.html</string>
    </array>" rewe-web-publish.launchd

echo "→ LaunchAgents (neu) laden"
for l in "${LABELS[@]}"; do
  launchctl bootout "$DOMAIN/$l" 2>/dev/null || true
done
sleep 1
for l in "${LABELS[@]}"; do plutil -lint -s "$AGENTS/$l.plist"; done
for l in "${LABELS[@]}"; do launchctl bootstrap "$DOMAIN" "$AGENTS/$l.plist"; done

echo "→ Healthcheck"
for i in $(seq 1 20); do
  if curl -fsS --max-time 3 http://127.0.0.1:7332/api/v1/rewe/status >/dev/null 2>&1; then echo "   ✓ http://127.0.0.1:7332/api/v1/rewe/status"; exit 0; fi
  sleep 0.5
done
echo "   ✗ http://127.0.0.1:7332/api/v1/rewe/status antwortet nicht – siehe $LOGS/rewe-api-error.log"
