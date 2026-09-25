#!/bin/bash
# REWE-Online-Fassung – läuft bei jedem neuen Bericht (LaunchAgent com.marc.rewe-web-publish, WatchPaths auf rewe_report.html):
# Bericht, Bon-PDFs und die Seite „Letzte Einkäufe“ auf rewe.timelapseffm-cloud.de veröffentlichen.
# Code aus diesem Repo (CODE_DIR), Daten aus REWE_DATA_DIR (~/Library/Application Support/Rewe).
set -euo pipefail

CODE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="${REWE_DATA_DIR:-$HOME/Library/Application Support/Rewe}"
export REWE_DATA_DIR="$DATA_DIR"
REMOTE="allinkl:/www/htdocs/w021e603/rewe.timelapseffm-cloud.de/"
REMOTE_DIR="/www/htdocs/w021e603/rewe.timelapseffm-cloud.de"
PYTHON="/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"
STAGING_DIR=$(/usr/bin/mktemp -d /tmp/rewe-web-publish.XXXXXX)
trap '/bin/rm -rf "$STAGING_DIR"' EXIT

"$PYTHON" "$CODE_DIR/scripts/generate-last-page.py"
"$PYTHON" "$CODE_DIR/scripts/prepare-web.py"
/bin/cp "$DATA_DIR/rewe_report.html" "$STAGING_DIR/dashboard.php"
/bin/cp "$CODE_DIR/web/receipt-pdf.php" "$STAGING_DIR/receipt-pdf.php"
/usr/bin/perl -0777 -pi -e '$_ = qq{<?php require __DIR__ . "/auth.php"; require_rewe_login(); ?>\n} . $_' "$STAGING_DIR/dashboard.php"
/usr/bin/perl -0pi -e 's~<body>~<body><a href="/logout.php" style="position:fixed;top:12px;right:14px;z-index:9999;padding:8px 11px;border-radius:999px;background:#fff;color:#555;text-decoration:none;font:600 13px -apple-system,BlinkMacSystemFont,\047Segoe UI\047,sans-serif;box-shadow:0 2px 10px #0002">Abmelden</a>~' "$STAGING_DIR/dashboard.php"
/bin/cp "$DATA_DIR/groups.json" "$STAGING_DIR/groups.json"
if [ -f "$DATA_DIR/categories_override.json" ]; then
    /bin/cp "$DATA_DIR/categories_override.json" "$STAGING_DIR/categories_override.json"
else
    printf '{}\n' >"$STAGING_DIR/categories_override.json"
fi

/usr/bin/perl -0pi -e 's#http://localhost:7331/save-groups#save-groups.php#g; s#http://localhost:7331/save-cat-override#save-categories.php#g' "$STAGING_DIR/dashboard.php"
/usr/bin/scp -q "$STAGING_DIR/dashboard.php" "$STAGING_DIR/receipt-pdf.php" "$STAGING_DIR/groups.json" "$STAGING_DIR/categories_override.json" "$REMOTE"
/usr/bin/scp -q -r "$DATA_DIR/web/pdfs" "$REMOTE"
/usr/bin/scp -q -r "$DATA_DIR/web/last" "$REMOTE"
/usr/bin/ssh -o BatchMode=yes allinkl "chmod 755 '$REMOTE_DIR/pdfs'; find '$REMOTE_DIR/pdfs' -maxdepth 1 -type f -name '*.pdf' -exec chmod 644 {} +; chmod 644 '$REMOTE_DIR/pdfs/.htaccess' '$REMOTE_DIR/receipt-pdf.php'"
