#!/bin/bash
cd "$(dirname "$0")"
export PATH="$HOME/bin:$PATH"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  GitHub Einrichtung"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Schritt 1: GitHub-Login (Browser öffnet sich)"
echo ""
gh auth login --web -h github.com

echo ""
echo "Schritt 2: Privates Repo erstellen & hochladen"
gh repo create rewe-ebon-analyse --private --source=. --push

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Fertig! Repo ist jetzt auf GitHub."
gh repo view --web
