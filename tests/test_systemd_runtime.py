"""User-manager recovery checks without changing accounts or system services."""

import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".devcontainer/scripts/ensure-systemd-user-manager.sh"

GUARD = r'''
id() { case "$1" in -un) echo "${TEST_USER:-vscode}";; -u) echo 1000;; esac; }
cat() { if [[ "$1" == /proc/1/comm ]]; then echo "${TEST_INIT:-systemd}"; else command cat "$@"; fi; }
stat() { echo "${TEST_SHADOW:-0:600}"; }
sudo() {
    printf 'sudo %s\n' "$*" >> "$CALL_LOG"
    [[ "${TEST_SUDO:-available}" == available ]] || return 1
    if [[ "$*" == "-n systemctl start "* ]]; then
        [[ "${TEST_START:-healthy}" == healthy ]] || return 1
        touch "$MANAGER_STARTED"
    fi
}
systemctl() {
    printf 'systemctl %s\n' "$*" >> "$CALL_LOG"
    case "$*" in
        "is-active --quiet ror-vscode-user-manager.service")
            [[ "${TEST_SETUP:-active}" == active || -f "$MANAGER_STARTED" ]];;
        "is-active --quiet user@1000.service")
            [[ "${TEST_MANAGER:-active}" == active || -f "$MANAGER_STARTED" ]];;
        "--user is-active --quiet default.target")
            [[ "${TEST_CONNECTION:-healthy}" == healthy ]];;
        "status user@1000.service --no-pager") echo 'status=224/PAM';;
        *) return 1;;
    esac
}
busctl() { [[ "${TEST_BUS:-healthy}" == healthy ]]; }
loginctl() { echo "${TEST_LINGER:-yes}"; }
'''


class SystemdRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.bus = socket.socket(socket.AF_UNIX)
        self.addCleanup(self.bus.close)
        self.bus.bind(str(self.directory / "bus"))
        self.guard = self.directory / "guard.sh"
        self.guard.write_text(GUARD)
        self.log = self.directory / "calls"
        self.environment = dict(
            os.environ, XDG_RUNTIME_DIR=str(self.directory),
            BASH_ENV=str(self.guard), CALL_LOG=str(self.log),
            MANAGER_STARTED=str(self.directory / "started"),
        )

    def run_script(self, script=SCRIPT, **overrides):
        result = subprocess.run(
            ["/bin/bash", str(script)], env=dict(self.environment, **overrides),
            text=True, capture_output=True, timeout=5,
        )
        calls = self.log.read_text().splitlines() if self.log.exists() else []
        return result, calls

    def test_failed_manager_recovers_after_root_only_shadow_repair(self):
        result, calls = self.run_script(
            TEST_SHADOW="0:0", TEST_SETUP="failed", TEST_MANAGER="failed",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        repair = calls.index("sudo -n chmod 0600 /etc/shadow")
        start = calls.index("sudo -n systemctl start ror-vscode-user-manager.service")
        self.assertLess(repair, start)
        self.assertIn("manager and bus are ready", result.stdout)
        self.assertFalse(any("restart" in call or "brew " in call for call in calls))

    def test_healthy_runtime_needs_no_privileged_changes(self):
        result, calls = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(call.startswith("sudo ") for call in calls))

    def test_other_shadow_permissions_and_owners_are_preserved(self):
        for metadata in ("0:640", "0:400", "1000:0"):
            with self.subTest(metadata=metadata):
                self.log.unlink(missing_ok=True)
                result, calls = self.run_script(TEST_SHADOW=metadata)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(any("chmod" in call for call in calls))

    def test_active_setup_unit_does_not_hide_a_failed_user_manager(self):
        result, calls = self.run_script(TEST_MANAGER="failed")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("sudo -n systemctl start user@1000.service", calls)

    def test_unavailable_permission_repair_stops_before_start(self):
        result, calls = self.run_script(TEST_SHADOW="0:0", TEST_SUDO="unavailable")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Cannot repair /etc/shadow permissions", result.stderr)
        self.assertFalse(any("systemctl start" in call for call in calls))

    def test_failed_start_reports_pam_status_and_journal_command(self):
        result, _ = self.run_script(TEST_SETUP="failed", TEST_START="broken")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("224/PAM", result.stderr)
        self.assertIn("sudo journalctl -b -u user@1000.service", result.stderr)
        self.assertNotIn("are ready", result.stdout)

    def test_socket_and_bus_connectivity_are_required(self):
        for overrides, message in (
            ({"TEST_BUS": "broken"}, "user bus"),
            ({"TEST_CONNECTION": "broken"}, "user manager"),
            ({"TEST_LINGER": "no"}, "lingering"),
        ):
            with self.subTest(overrides=overrides):
                result, _ = self.run_script(**overrides)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertNotIn("are ready", result.stdout)
        (self.directory / "bus").unlink()
        result, _ = self.run_script()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("user bus is missing", result.stderr)

    def test_wrong_user_or_init_prevents_privileged_changes(self):
        for overrides in ({"TEST_USER": "root"}, {"TEST_INIT": "tini"}):
            with self.subTest(overrides=overrides):
                result, calls = self.run_script(**overrides)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(any(call.startswith("sudo ") for call in calls))

    def test_startup_requires_user_manager_before_review_setup(self):
        scripts = self.directory / "scripts"
        scripts.mkdir()
        startup = scripts / "ensure-review-runtime.sh"
        shutil.copyfile(ROOT / ".devcontainer/scripts/ensure-review-runtime.sh", startup)
        for filename, label in (
            ("ensure-systemd-user-manager.sh", "manager"),
            ("check-review-runtime.sh", "review"),
            ("stage-josh-room.sh", "extension"),
            ("configure-codex.sh", "configuration"),
        ):
            (scripts / filename).write_text(
                f'printf "{label}\\n" >> "$CALL_LOG"\n'
                + ('exit "${TEST_RUNTIME_STATUS:-0}"\n' if label == "manager" else ""),
            )
        result, calls = self.run_script(startup, TEST_RUNTIME_STATUS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, ["manager"])
        self.log.unlink()
        result, calls = self.run_script(startup)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ["manager", "review", "extension", "configuration"])


if __name__ == "__main__":
    unittest.main()
