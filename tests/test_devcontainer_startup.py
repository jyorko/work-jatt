"""Regression checks for SSH PATH and the post-start timezone bind."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DevcontainerStartupTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / ".devcontainer/devcontainer.json").read_text())

    def test_ssh_shell_finds_bash_and_git_with_builder_path(self):
        zsh = shutil.which("zsh")
        if not zsh:
            self.skipTest("zsh is required to reproduce the Remote-SSH shell")
        # Dockerless leaves this PATH behind even after the Wolfi build completes.
        env = dict(os.environ, PATH="/usr/local/bin:/.dockerless:/.dockerless/bin")
        env.update(self.config["containerEnv"])
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "gitconfig"
            env["TEST_GITCONFIG"] = str(config)
            result = subprocess.run(
                [zsh, "-c", "bash -c 'printf ssh-ready' && "
                 'git config --file "$TEST_GITCONFIG" user.name regression-user'],
                env=env, capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "ssh-ready")
            self.assertIn("name = regression-user", config.read_text())

    def test_post_start_repairs_timezone_before_runtime_check(self):
        with tempfile.TemporaryDirectory(prefix="workspace with spaces ") as folder:
            root = Path(folder)
            scripts = root / ".devcontainer/scripts"
            scripts.mkdir(parents=True)
            localtime = root / "localtime"
            # Replace privileged writes at the boundary, but perform the real ln.
            bin_dir = root / "bin"
            bin_dir.mkdir()
            sudo = bin_dir / "sudo"
            sudo.write_text("#!/bin/sh\n"
                            "test \"$1\" = -n || exit 90\nshift\n"
                            "test \"$1\" = ln || exit 91\nshift\n"
                            "test \"$3\" = /etc/localtime || exit 92\n"
                            "exec /bin/ln \"$1\" \"$2\" \"$TEST_LOCALTIME\"\n")
            sudo.chmod(0o755)
            check = scripts / "ensure-review-runtime.sh"
            check.write_text("#!/bin/bash\n"
                             "test -L \"$TEST_LOCALTIME\" || exit 93\n"
                             "test \"$(readlink \"$TEST_LOCALTIME\")\" = /usr/share/zoneinfo/Etc/UTC || exit 94\n"
                             "printf runtime-ready\n")
            command = [arg.replace("${containerWorkspaceFolder}", str(root))
                       for arg in self.config["postStartCommand"]]
            env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}",
                       TEST_LOCALTIME=str(localtime))
            # Repeat after corrupting the link to exercise restart convergence.
            for target in (None, "/wrong/timezone"):
                if target:
                    localtime.unlink()
                    localtime.symlink_to(target)
                result = subprocess.run(command, env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, "runtime-ready")

            sudo.write_text("#!/bin/sh\nexit 77\n")
            result = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 77)
            self.assertNotIn("runtime-ready", result.stdout)


if __name__ == "__main__":
    unittest.main()
