#!/bin/bash
# REWE eBon Auswertung – einfach doppelklicken!
cd "$(dirname "$0")"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  REWE eBon Auswertung"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Neue EML-Dateien in 'import/' ablegen,"
echo "dann läuft die Auswertung automatisch."
echo ""

python3 rewe_analyze.py

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Fertig! Bericht wird geöffnet..."
open "rewe_report.html"
