"""Offline release-update checks. Run: python3 -m unittest discover -s tests -v."""

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = b"test release VSIX"
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()


class JoshRoomUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "workspace with spaces"
        for folder in (".devcontainer", ".vscode"):
            shutil.copytree(ROOT / folder, self.root / folder)
        self.pin = self.root / ".devcontainer/josh-room.env"
        self.original_pin = self.pin.read_bytes()
        self.cache = self.root / "cache"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.env = dict(os.environ, JOSH_ROOM_CACHE_DIR=str(self.cache),
                        PATH=f"{self.bin}:{os.environ['PATH']}",
                        TEST_DIGEST=DIGEST, TEST_PAYLOAD=PAYLOAD.decode())
        curl = self.bin / "curl"
        curl.write_text('''#!/usr/bin/env bash
set -euo pipefail
for arg in "$@"; do
  if [[ "$arg" == */SHA256SUMS ]]; then
    printf '%s  josh-room-0.1.99.vsix\\n' "$TEST_DIGEST"
    exit 0
  fi
done
while [ "$#" -gt 0 ]; do
  if [ "$1" = --output ]; then
    printf '%s' "$TEST_PAYLOAD" > "$2"
    exit 0
  fi
  shift
done
exit 22
''')
        curl.chmod(0o755)

    def run_script(self, script, *args):
        return subprocess.run(["bash", str(self.root / script), *args],
                              env=self.env, capture_output=True, text=True)

    def update(self, *args):
        return self.run_script(".vscode/update-josh-room.sh", *args)

    def test_release_checksum_discovery_and_idempotent_staging(self):
        result = self.update("v0.1.99-standalone-vsix")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('VERSION="0.1.99"', self.pin.read_text())
        stable = self.cache / "josh-room.vsix"
        self.assertEqual(stable.read_bytes(), PAYLOAD)
        # A valid version cache must repair the stable file without downloading.
        stable.write_bytes(b"corrupt")
        (self.bin / "curl").write_text("#!/usr/bin/env bash\nexit 99\n")
        result = self.run_script(".devcontainer/scripts/stage-josh-room.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(stable.read_bytes(), PAYLOAD)

    def test_explicit_checksum_and_corrupt_cache_repair(self):
        self.cache.mkdir()
        (self.cache / "josh-room-0.1.99.vsix").write_bytes(b"corrupt")
        result = self.update("0.1.99", DIGEST)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.cache / "josh-room-0.1.99.vsix").read_bytes(), PAYLOAD)

    def test_checksum_mismatch_preserves_pin_and_staged_extension(self):
        self.cache.mkdir()
        stable = self.cache / "josh-room.vsix"
        stable.write_bytes(b"previous release")
        result = self.update("0.1.99", "0" * 64)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("checksum verification failed", result.stderr)
        self.assertEqual(self.pin.read_bytes(), self.original_pin)
        self.assertEqual(stable.read_bytes(), b"previous release")
        self.assertFalse((self.cache / "josh-room-0.1.99.vsix").exists())
        self.assertFalse(list(self.pin.parent.glob("josh-room.env.*")))
        self.assertFalse(list(self.cache.glob(".josh-room-*")))

    def test_missing_release_checksum_preserves_pin(self):
        self.env["TEST_DIGEST"] = ""
        result = self.update("0.1.99")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.pin.read_bytes(), self.original_pin)

    def test_invalid_version_preserves_pin(self):
        result = self.update("../../invalid")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.pin.read_bytes(), self.original_pin)

    def test_ready_runtime_stages_extension_on_start(self):
        result = self.update("0.1.99", DIGEST)
        self.assertEqual(result.returncode, 0, result.stderr)
        stable = self.cache / "josh-room.vsix"
        stable.unlink()
        check = self.root / ".devcontainer/scripts/check-review-runtime.sh"
        check.write_text("#!/usr/bin/env bash\nexit 0\n")
        result = self.run_script(".devcontainer/scripts/ensure-review-runtime.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(stable.read_bytes(), PAYLOAD)

    def test_installer_uses_shared_pin_and_verified_asset(self):
        result = self.update("0.1.99", DIGEST)
        self.assertEqual(result.returncode, 0, result.stderr)
        code = self.bin / "code-insiders"
        code.write_text('''#!/usr/bin/env bash
set -euo pipefail
if [ "$1" = --list-extensions ]; then
  echo 'joshyorko.josh-room@0.1.24'
else
  test "$1" = --install-extension
  test "$2" = "$JOSH_ROOM_CACHE_DIR/josh-room-0.1.99.vsix"
  test "$3" = --force
  test -f "$2"
fi
''')
        code.chmod(0o755)
        shutil.copy2(code, self.bin / "code")
        result = self.run_script(".vscode/install-josh-room.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Installed Josh Room 0.1.99", result.stdout)
