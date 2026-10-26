"""Offline checks for the stable Review bootstrap contract."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReviewBootstrapTests(unittest.TestCase):
    def run_script(self, name, guard_text, **extra_env):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            guard = home / "guard.sh"
            guard.write_text(guard_text)
            log = home / "calls"
            env = dict(os.environ, HOME=str(home), BASH_ENV=str(guard), CALL_LOG=str(log))
            env.update(extra_env)
            result = subprocess.run(["bash", str(ROOT / ".devcontainer/scripts" / name)],
                                    env=env, capture_output=True, text=True)
            return result, log.read_text().splitlines()

    def test_install_avoids_whole_tap_validation(self):
        result, calls = self.run_script("install-review-package.sh", '''brew() {
  printf '%s\\n' "$*" >> "$CALL_LOG"
  if [[ "$1" == tap ]]; then
    echo "Cannot tap joshyorko/tools: invalid syntax in tap!" >&2
    return 1
  fi
  if [[ "$1" == list ]]; then return 1; fi
}
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ["update",
                                 "trust --formula joshyorko/tools/review",
                                 "list --versions joshyorko/tools/review",
                                 "install joshyorko/tools/review"])

    def test_install_upgrades_existing_stable_review_formula(self):
        result, calls = self.run_script("install-review-package.sh", '''brew() {
  printf '%s\\n' "$*" >> "$CALL_LOG"
}
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ["update", "trust --formula joshyorko/tools/review",
                                 "list --versions joshyorko/tools/review",
                                 "upgrade joshyorko/tools/review"])

    def test_shared_omp_configuration_uses_current_launcher_variable(self):
        config = json.loads((ROOT / ".devcontainer/devcontainer.json").read_text())
        self.assertEqual(config["containerEnv"]["REVIEW_RUNTIME"], "auto")
        self.assertEqual(config["containerEnv"]["REVIEW_INHERIT_OMP_CONFIG"], "1")
        self.assertEqual(config["containerEnv"]["LUNA_FACTORY_ENABLED"], "1")
        self.assertEqual(config["containerEnv"]["LUNA_FACTORY_CAPACITY"], "3")
        self.assertNotIn("REVIEW_TEST_KVM_DEVICE", config["containerEnv"])
        self.assertFalse(any(key.startswith("BLUEFIN_") for key in config["containerEnv"]))
