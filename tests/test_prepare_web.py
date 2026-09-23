import subprocess
import sys
import tempfile
import unittest
import stat
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts" / "prepare-web.py"


class PrepareWebTest(unittest.TestCase):
    def test_copies_every_receipt_pdf_into_the_publishable_web_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pdfs").mkdir()
            (root / "web").mkdir()
            source = root / "pdfs" / "2026-09-08_13-07-59.pdf"
            source.write_bytes(b"%PDF-test")
            source.chmod(0o600)

            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--root", str(root)],
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                (root / "web" / "pdfs" / "2026-09-08_13-07-59.pdf").read_bytes(),
                b"%PDF-test",
            )
            self.assertEqual(
                stat.S_IMODE((root / "web" / "pdfs").stat().st_mode),
                0o755,
            )
            self.assertEqual(
                stat.S_IMODE(
                    (root / "web" / "pdfs" / "2026-09-08_13-07-59.pdf").stat().st_mode
                ),
                0o644,
            )


if __name__ == "__main__":
    unittest.main()
