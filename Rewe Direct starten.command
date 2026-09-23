#!/bin/bash
# REWE Direct – eBons direkt vom Rewe-Konto laden
cd "$(dirname "$0")"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  REWE Direct – API-Import"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Lädt neue eBons direkt von deinem Rewe-Konto."
echo "Beim ersten Start: korb login ausführen!"
echo ""

python3 rewe_direct.py --serve

echo ""
echo "Fertig."
