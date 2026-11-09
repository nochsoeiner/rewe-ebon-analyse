import importlib.util
import plistlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "install_offer_job", Path(__file__).resolve().parents[1] / "scripts/install-offer-job.py")
job = importlib.util.module_from_spec(spec)
spec.loader.exec_module(job)


class OfferJobTest(unittest.TestCase):
    def test_installed_schedule_runs_only_sunday_and_preserves_other_jobs(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            agents = home / "Library/LaunchAgents"
            agents.mkdir(parents=True)
            existing = agents / "com.marc.rewe-web-update.plist"
            existing.write_bytes(b"existing job")
            code = home / "Code & Angebote"
            data = home / "Application Support/Rewe"
            with patch.object(job.subprocess, "run") as run:
                path = job.install(code, data, home, "/test/python3", load=False)
            run.assert_not_called()
            installed = plistlib.loads(path.read_bytes())
            self.assertEqual(installed["StartCalendarInterval"],
                             {"Weekday": 0, "Hour": 18, "Minute": 0})
            self.assertNotIn("StartInterval", installed)
            self.assertNotIn("RunAtLoad", installed)
            self.assertEqual(installed["ProgramArguments"],
                             ["/test/python3", str(code / "rewe_offer_refresh.py")])
            self.assertEqual(installed["EnvironmentVariables"]["REWE_DATA_DIR"], str(data))
            self.assertEqual(existing.read_bytes(), b"existing job")

    def test_loaded_job_is_replaced_without_starting_a_fetch(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            with patch.object(job.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
                path = job.install(home, home / "Data", home, "/test/python3")
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual([command[1] for command in commands], ["print", "bootout", "bootstrap"])
            self.assertEqual(commands[-1][-1], str(path))

    def test_bootstrap_failure_is_not_reported_as_installed(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            with patch.object(job.subprocess, "run", side_effect=[
                subprocess.CompletedProcess([], 113),
                subprocess.CalledProcessError(5, ["launchctl", "bootstrap"]),
            ]):
                with self.assertRaises(subprocess.CalledProcessError):
                    job.install(home, home / "Data", home, "/test/python3")
