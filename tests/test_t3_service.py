"""Task boundary checks and real Linux procfs/socket verification."""

import fcntl
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location("t3_checks", ROOT / ".vscode/check-t3-service.py")
CHECKS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKS)

GUARD = r'''
set -E
id() { case "$1" in -un) echo "${TEST_USER:-vscode}";; -u) echo 1000;; esac; }
cat() { if [[ "$1" == /proc/1/comm ]]; then echo "${TEST_INIT:-systemd}"; else command cat "$@"; fi; }
loginctl() { echo yes; }
busctl() { [[ "${TEST_BUS:-healthy}" == healthy ]]; }
systemctl() {
    printf 'systemctl %s\n' "$*" >> "$CALL_LOG"
    case "$*" in
        is-system-running) echo "${TEST_STATE:-running}";;
        *--property=MainPID*) echo 4321;;
        *is-active*) [[ "${TEST_MANAGER:-healthy}" == healthy ]];;
    esac
}
brew() {
    printf 'brew %s\n' "$*" >> "$CALL_LOG"
    case "$1" in
        list) [[ "${TEST_INSTALLED:-no}" == yes ]];;
        --prefix) echo /tmp/test-t3-keg;;
        services) [[ "${TEST_START:-healthy}" == healthy ]];;
        trust|install) return 0;;
        *) return 1;;
    esac
}
python3() {
    printf 'check %s\n' "$2" >> "$CALL_LOG"
    if [[ "$2" == preflight && "${TEST_CONFLICT:-no}" == yes ]]; then
        echo 'Competing T3 server. No process was stopped.' >&2
        return 1
    fi
    if [[ "$2" == verify && "${TEST_READY:-yes}" == no ]]; then
        echo 'The service MainPID owns no TCP listener yet.' >&2
        return 1
    fi
    echo 'MainPID=4321, UID=1000, one T3 server, owned TCP port(s)=[3773].'
}
sleep() { SECONDS=$((SECONDS + 1)); }
'''


class TaskTests(unittest.TestCase):
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

    def run_task(self, **overrides):
        environment = dict(os.environ, HOME="/home/vscode", XDG_RUNTIME_DIR=str(self.directory),
                           BASH_ENV=str(self.guard), CALL_LOG=str(self.log))
        environment.update(overrides)
        result = subprocess.run(["/bin/bash", str(ROOT / ".vscode/install-t3-service.sh")],
                                env=environment, text=True, capture_output=True, timeout=5)
        calls = self.log.read_text().splitlines() if self.log.exists() else []
        return result, calls

    def test_task_is_a_finite_manual_process(self):
        tasks = json.loads((ROOT / ".vscode/tasks.json").read_text())["tasks"]
        task = next(task for task in tasks if task["label"] == "T3: Install and start service")
        self.assertEqual(task["type"], "process")
        self.assertEqual(task["command"], "/bin/bash")
        self.assertEqual(task["args"], ["${workspaceFolder}/.vscode/install-t3-service.sh"])
        self.assertEqual(task["problemMatcher"], [])
        self.assertEqual(task["runOptions"].get("instanceLimit"), 1)
        self.assertNotIn("runOn", task["runOptions"])
        self.assertFalse(task.get("isBackground", False))

    def test_fresh_install_starts_and_verifies_the_homebrew_service(self):
        result, calls = self.run_task()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("brew install --formula joshyorko/tools/t3code-cli-main", calls)
        self.assertIn("brew services start joshyorko/tools/t3code-cli-main", calls)
        self.assertIn("check verify", calls)
        self.assertIn("PASS:", result.stdout)

    def test_existing_install_is_not_upgraded_or_restarted(self):
        result, calls = self.run_task(TEST_INSTALLED="yes")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any(call.startswith(("brew install", "brew upgrade", "brew trust")) for call in calls))
        self.assertFalse(any("restart" in call or "stop" in call for call in calls))

    def test_prerequisite_failures_happen_before_homebrew(self):
        for overrides, message in [
            ({"TEST_INIT": "tini"}, "issues/5"),
            ({"TEST_BUS": "broken"}, "user bus"),
            ({"TEST_MANAGER": "broken"}, "user manager"),
            ({"TEST_USER": "root"}, "non-root vscode"),
        ]:
            with self.subTest(overrides=overrides):
                self.log.unlink(missing_ok=True)
                result, calls = self.run_task(**overrides)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                self.assertFalse(any(call.startswith("brew ") for call in calls))

    def test_missing_bus_socket_fails_before_install(self):
        (self.directory / "bus").unlink()
        result, calls = self.run_task()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("user bus is missing", result.stderr)
        self.assertFalse(any(call.startswith("brew ") for call in calls))

    def test_degraded_system_is_visible_but_required_managers_suffice(self):
        result, calls = self.run_task(TEST_STATE="degraded")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WARNING:", result.stderr)
        self.assertIn("systemctl --failed --no-pager --plain", calls)

    def test_competing_server_is_not_stopped_or_installed_over(self):
        result, calls = self.run_task(TEST_CONFLICT="yes")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No process was stopped", result.stderr)
        self.assertFalse(any(call.startswith("brew ") for call in calls))

    def test_overlapping_setup_is_rejected(self):
        with (self.directory / "work-jatt-t3-service.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result, calls = self.run_task()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Another T3 service setup", result.stderr)
        self.assertFalse(any(call.startswith("brew ") for call in calls))

    def test_successful_start_without_listener_is_a_bounded_failure(self):
        result, calls = self.run_task(TEST_READY="no")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("within 30 seconds", result.stderr)
        self.assertIn("owns no TCP listener", result.stderr)
        self.assertNotIn("PASS:", result.stdout)
        self.assertLessEqual(calls.count("check verify"), 30)

    def test_failed_start_returns_diagnostics(self):
        result, calls = self.run_task(TEST_START="broken")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any("--property=ActiveState,SubState,Result,MainPID,ExecMainStatus,NRestarts" in call
                            for call in calls))
        self.assertNotIn("PASS:", result.stdout)


class ProcfsTests(unittest.TestCase):
    def setUp(self):
        # Keep the test's real process observations separate from host T3 sessions.
        self.pids = set()
        real_servers = CHECKS.servers
        scope = patch.object(CHECKS, "servers", side_effect=lambda: {
            pid: args for pid, args in real_servers().items() if pid in self.pids
        })
        scope.start()
        self.addCleanup(scope.stop)

    def start_server(self, listen=True, serve=True, extra=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        prefix = Path(temporary.name) / "t3code-cli-main"
        entry = prefix / "libexec/dist/bin.mjs"
        entry.parent.mkdir(parents=True)
        entry.touch()
        code = "import socket, time; s=socket.socket(); "
        code += "s.bind(('127.0.0.1', 0)); s.listen(); " if listen else ""
        code += "print('ready', flush=True); time.sleep(30)"
        arguments = (["serve"] if serve else []) + (extra or [])
        process = subprocess.Popen([sys.executable, "-u", "-c", code, str(entry)] + arguments,
                                   stdout=subprocess.PIPE, text=True)
        self.addCleanup(process.stdout.close)
        self.addCleanup(process.wait)
        self.addCleanup(process.terminate)
        self.pids.add(process.pid)
        self.assertEqual(process.stdout.readline().strip(), "ready")
        return process, prefix

    def test_real_mainpid_with_owned_listener_passes(self):
        process, prefix = self.start_server()
        CHECKS.check("verify", process.pid, str(prefix))

    def test_active_process_without_listener_fails(self):
        process, prefix = self.start_server(listen=False)
        with self.assertRaisesRegex(ValueError, "owns no TCP listener"):
            CHECKS.check("verify", process.pid, str(prefix))

    def test_another_process_listener_does_not_satisfy_readiness(self):
        process, prefix = self.start_server(listen=False)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            with self.assertRaisesRegex(ValueError, "owns no TCP listener"):
                CHECKS.check("verify", process.pid, str(prefix))

    def test_competing_server_fails_without_terminating_it(self):
        process, _ = self.start_server()
        with self.assertRaisesRegex(ValueError, "Competing T3 server"):
            CHECKS.check("preflight", 0)
        self.assertIsNone(process.poll())

    def test_default_cli_invocation_is_also_a_competing_server(self):
        process, _ = self.start_server(serve=False)
        with self.assertRaisesRegex(ValueError, "Competing T3 server"):
            CHECKS.check("preflight", 0)
        self.assertIsNone(process.poll())

    def test_unrelated_node_entrypoint_is_not_a_t3_server(self):
        self.assertFalse(CHECKS.is_server(["node", "/workspaces/catalog-api/dist/index.mjs"]))
        self.assertFalse(CHECKS.is_server(["node", "/workspaces/catalog-api/dist/bin.mjs", "t3"]))

    def test_supported_default_invocations_and_non_server_commands(self):
        entry = "/opt/Cellar/t3code-cli-main/1/libexec/dist/bin.mjs"
        for args in (["node", entry], ["node", entry, "/workspaces/project", "--port", "4000"],
                     ["node", entry, "--port=4000"]):
            with self.subTest(args=args):
                self.assertTrue(CHECKS.is_server(args))
        for command in ("--help", "--version", "pair", "auth", "thread"):
            with self.subTest(command=command):
                self.assertFalse(CHECKS.is_server(["node", entry, command]))

    def test_cwd_first_port_equals_process_is_competing_server(self):
        process, _ = self.start_server(serve=False, extra=["/workspaces/project", "--port=4000"])
        with self.assertRaisesRegex(ValueError, "Competing T3 server"):
            CHECKS.check("preflight", 0)
        self.assertIsNone(process.poll())

    def test_default_invocations_accept_other_supported_options(self):
        entry = "/opt/t3code-cli-main/libexec/dist/bin.mjs"
        for options in (
            ["--dev-url", "http://127.0.0.1:5173", "--port=4000"],
            ["--log-level", "debug", "--port=4000"],
            ["--base-dir", "/tmp/state", "/workspaces/project", "--port=4000"],
            ["--auto-bootstrap-project-from-cwd", "--port=4000"],
        ):
            with self.subTest(options=options):
                self.assertTrue(CHECKS.is_server(["node", entry, *options]))

    def test_non_server_commands_are_not_confused_with_server_arguments(self):
        entry = "/opt/t3code-cli-main/libexec/dist/bin.mjs"
        for options in (
            ["status"], ["browser", "status"], ["project", "list"],
            ["thread", "send", "serve"], ["--base-dir", "serve", "auth", "status"],
            ["--log-level", "debug", "pair"], ["-v"], ["--completions", "zsh"],
        ):
            with self.subTest(options=options):
                self.assertFalse(CHECKS.is_server(["node", entry, *options]))

    def test_second_supported_invocation_fails_duplicate_server_verification(self):
        service, prefix = self.start_server()
        duplicate, _ = self.start_server(serve=False, extra=["/workspaces/project", "--port", "4000"])
        with self.assertRaisesRegex(ValueError, "Competing T3 server"):
            CHECKS.check("verify", service.pid, str(prefix))
        self.assertIsNone(service.poll())
        self.assertIsNone(duplicate.poll())

    def test_default_port_conflict_fails_without_closing_listener(self):
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            # Map this real socket to the default port without occupying the host's T3 port.
            listening = {inode: 3773 for inode, port in CHECKS.listeners().items()
                         if port == listener.getsockname()[1]}
            self.assertTrue(listening)
            with patch.object(CHECKS, "listeners", return_value=listening), \
                    self.assertRaisesRegex(ValueError, "competing listener"):
                CHECKS.check("preflight", 0)
            self.assertGreater(listener.fileno(), 0)

    def test_wrong_formula_process_is_rejected(self):
        process, _ = self.start_server()
        with self.assertRaisesRegex(ValueError, "not the installed formula"):
            CHECKS.check("verify", process.pid, "/tmp/another-keg")


if __name__ == "__main__":
    unittest.main()
