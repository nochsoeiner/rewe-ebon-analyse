#!/usr/bin/env python3
"""Copy generated receipt assets into the directory published to the webspace."""

import argparse
import os
import shutil
from pathlib import Path


def prepare(root: Path) -> int:
    source_dir = root / "pdfs"
    target_dir = root / "web" / "pdfs"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_dir.chmod(0o755)

    copied = 0
    for source in source_dir.glob("*.pdf"):
        target = target_dir / source.name
        if not target.exists() or source.stat().st_mtime_ns != target.stat().st_mtime_ns:
            shutil.copy2(source, target)
            copied += 1
        os.chmod(target, 0o644)
    return copied


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    copied = prepare(args.root.resolve())
    print(f"Web-PDFs vorbereitet: {copied} kopiert")


if __name__ == "__main__":
    main()
