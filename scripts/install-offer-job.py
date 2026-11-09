#!/usr/bin/env python3
"""Installiert ausschließlich den REWE-Angebotsabruf (Sonntag + Nachtläufe) für macOS."""

import argparse
import os
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path


LABEL = "com.marc.rewe-offers"
# Sonntag 18:00 holt den neuen Angebotskatalog. Die Nachtläufe setzen einen von
# REWE gebremsten Abruf fort und suchen in kleinen Portionen Produkt-IDs.
SCHEDULE = [
    {"Weekday": 0, "Hour": 18, "Minute": 0},
    {"Hour": 1, "Minute": 30},
    {"Hour": 3, "Minute": 0},
    {"Hour": 4, "Minute": 30},
]


def launchagent(code_dir: Path, data_dir: Path, home: Path, python: str) -> dict:
    return {
        "Label": LABEL,
        "ProgramArguments": [python, str(code_dir / "rewe_offer_refresh.py"), "--scheduled"],
        "WorkingDirectory": str(data_dir),
        "EnvironmentVariables": {"REWE_DATA_DIR": str(data_dir), "PYTHONUNBUFFERED": "1"},
        "StartCalendarInterval": SCHEDULE,
        "ProcessType": "Background",
        "StandardOutPath": str(home / "Library/Logs/rewe-offers.log"),
        "StandardErrorPath": str(home / "Library/Logs/rewe-offers-error.log"),
    }


def install(code_dir: Path, data_dir: Path, home: Path, python: str, load: bool = True) -> Path:
    agent_dir = home / "Library/LaunchAgents"
    agent_dir.mkdir(parents=True, exist_ok=True)
    (home / "Library/Logs").mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    destination = agent_dir / f"{LABEL}.plist"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{LABEL}.", dir=agent_dir)
    try:
        with os.fdopen(descriptor, "wb") as output:
            plistlib.dump(launchagent(code_dir, data_dir, home, python), output)
        Path(temporary).chmod(0o644)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    if load:
        domain = f"gui/{os.getuid()}"
        target = f"{domain}/{LABEL}"
        current = subprocess.run(["/bin/launchctl", "print", target], capture_output=True)
        if current.returncode == 0:
            subprocess.run(["/bin/launchctl", "bootout", target], check=True)
        subprocess.run(["/bin/launchctl", "bootstrap", domain, str(destination)], check=True)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-only", action="store_true", help="Nur die plist schreiben, nicht laden")
    args = parser.parse_args()
    home = Path.home()
    data_dir = Path(os.environ.get("REWE_DATA_DIR", home / "Library/Application Support/Rewe")).resolve()
    path = install(Path(__file__).resolve().parents[1], data_dir, home, sys.executable,
                   load=not args.write_only)
    print(f"REWE-Angebotsabruf: sonntags 18:00 Uhr, Nachtläufe 1:30/3:00/4:30 Uhr (lokale Mac-Zeit), {path}")


if __name__ == "__main__":
    main()
