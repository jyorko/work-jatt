"""github.com git credential setup and its non-interactive runtime check."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".devcontainer/scripts"
DEVSY_HELPER = "!'/usr/local/bin/devsy' internal agent git-credentials --port 12049"

# A stand-in for gh that records authentication checks. Git configuration and
# credential filling use the real git binary against the test's temporary HOME.
CONFIGURE_GUARD = r'''
command() {
    if [[ "$1" == -v && "$2" == gh ]]; then
        [[ "${TEST_GH:-authenticated}" == missing ]] && return 1
        printf '%s\n' "$TEST_GH_PATH"
        return 0
    fi
    builtin command "$@"
}
gh() {
    printf 'gh %s\n' "$*" >> "$CALL_LOG"
    [[ "$1 $2" == "auth token" && "${TEST_GH:-authenticated}" == authenticated ]]
}
'''

CHECK_GUARD = r'''
brew() { echo 'review 1.0.0'; }
for name in gh apptainer squashfuse gocryptfs fuse2fs review yq codex; do
    eval "${name}() { :; }"
done
timeout() { shift; "$@"; }
git() {
    printf 'git %s GIT_TERMINAL_PROMPT=%s\n' "$*" "${GIT_TERMINAL_PROMPT:-}" >> "$CALL_LOG"
    case "$1" in
        credential)
            command cat >/dev/null
            if [[ "${TEST_CREDENTIALS:-yes}" == yes ]]; then
                printf 'protocol=https\nhost=github.com\nusername=x-access-token\npassword=gho_secret_token\n'
            else
                echo "fatal: could not read Username for 'https://github.com': terminal prompts disabled" >&2
                return 128
            fi;;
        ls-remote) [[ "${TEST_REMOTE:-yes}" == yes ]];;
        -C) echo "${TEST_ORIGIN-https://github.com/jyorko/work-jatt}";;
    esac
}
'''


class GitHubGitTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.log = self.directory / "calls"
        self.gh_path = self.directory / "fake-gh"
        self.write_fake_gh(self.gh_path)
        self.environment = dict(
            os.environ, HOME=str(self.directory), XDG_CONFIG_HOME=str(self.directory / "config"),
            GIT_CONFIG_NOSYSTEM="1", CALL_LOG=str(self.log), TEST_GH_PATH=str(self.gh_path),
        )
        for name in ("GH_TOKEN", "GITHUB_TOKEN", "GIT_CONFIG_GLOBAL", "GITHUB_GIT_CHECK_REPOSITORY"):
            self.environment.pop(name, None)
        self.git("config", "--global", "credential.helper", DEVSY_HELPER)

    def git(self, *arguments, input=None):
        return subprocess.run(["git", *arguments], env=self.environment, text=True,
                              input=input, capture_output=True, check=True).stdout

    @staticmethod
    def write_fake_gh(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "#!/bin/sh\n"
            "if [ \"$1 $2\" = 'auth git-credential' ]; then\n"
            "  printf 'protocol=https\\nhost=github.com\\nusername=x-access-token\\npassword=test-gh-token\\n'\n"
            "fi\n"
        )
        path.chmod(0o755)

    @staticmethod
    def expected_helper(path):
        path = str(path)
        if any(character in path for character in (" ", "$", "\\")):
            return f"!'{path}' auth git-credential"
        return f"!{path} auth git-credential"

    def run_script(self, name, guard, **overrides):
        guard_file = self.directory / "guard.sh"
        guard_file.write_text(guard)
        self.log.unlink(missing_ok=True)
        result = subprocess.run(
            ["/bin/bash", str(SCRIPTS / name)],
            env=dict(self.environment, BASH_ENV=str(guard_file), **overrides),
            text=True, capture_output=True, timeout=10,
        )
        calls = self.log.read_text().splitlines() if self.log.exists() else []
        return result, calls

    def github_helpers(self):
        return self.git("config", "--global", "--get-all", "credential.https://github.com.helper").splitlines()

    def test_authenticated_gh_is_scoped_to_github_and_keeps_devsy(self):
        result, calls = self.run_script("configure-github-git.sh", CONFIGURE_GUARD)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, ["gh auth token --hostname github.com"])
        self.assertEqual(self.github_helpers(), ["", self.expected_helper(self.gh_path)])
        self.assertEqual(self.git("config", "--global", "credential.helper").strip(), DEVSY_HELPER)
        self.assertNotIn("test-gh-token", result.stdout + result.stderr)

    def test_repeated_runs_leave_the_configuration_alone(self):
        self.run_script("configure-github-git.sh", CONFIGURE_GUARD)
        before = (self.directory / ".gitconfig").read_text()
        result, calls = self.run_script("configure-github-git.sh", CONFIGURE_GUARD)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("already uses gh", result.stdout)
        self.assertEqual(calls, ["gh auth token --hostname github.com"])
        self.assertEqual((self.directory / ".gitconfig").read_text(), before)

    def test_helper_for_another_gh_path_is_replaced(self):
        self.git("config", "--global", "--add", "credential.https://github.com.helper", "")
        self.git("config", "--global", "--add", "credential.https://github.com.helper",
                 "!/old/prefix/gh auth git-credential")
        result, calls = self.run_script("configure-github-git.sh", CONFIGURE_GUARD)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.github_helpers(), ["", self.expected_helper(self.gh_path)])

    def test_trailing_empty_helper_is_repaired_and_git_reaches_gh(self):
        expected = self.expected_helper(self.gh_path)
        self.git("config", "--global", "--add", "credential.https://github.com.helper", "")
        self.git("config", "--global", "--add", "credential.https://github.com.helper", expected)
        self.git("config", "--global", "--add", "credential.https://github.com.helper", "")

        result, _ = self.run_script("configure-github-git.sh", CONFIGURE_GUARD)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.github_helpers(), ["", expected])
        credentials = self.git(
            "credential", "fill", input="protocol=https\nhost=github.com\n\n"
        )
        self.assertIn("username=x-access-token", credentials)
        self.assertIn("password=test-gh-token", credentials)

    def test_existing_gist_helper_is_unchanged(self):
        self.git("config", "--global", "--add", "credential.https://gist.github.com.helper", "!/old/gist-helper")
        before = self.git("config", "--global", "--get-all",
                          "credential.https://gist.github.com.helper")

        result, _ = self.run_script("configure-github-git.sh", CONFIGURE_GUARD)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git("config", "--global", "--get-all",
                                  "credential.https://gist.github.com.helper"), before)

    def test_gh_path_with_space_is_single_quoted(self):
        spaced_path = self.directory / "fake gh"
        self.write_fake_gh(spaced_path)
        result, _ = self.run_script("configure-github-git.sh", CONFIGURE_GUARD,
                                    TEST_GH_PATH=str(spaced_path))
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = self.expected_helper(spaced_path)
        self.assertEqual(self.github_helpers(), ["", expected])
        credentials = self.git("credential", "fill", input="protocol=https\nhost=github.com\n\n")
        self.assertIn("password=test-gh-token", credentials)

    def test_unauthenticated_or_missing_gh_prints_next_step_without_failing(self):
        for state, message in (("unauthenticated", "Next: gh auth login"), ("missing", "gh is not installed")):
            with self.subTest(state=state):
                result, calls = self.run_script("configure-github-git.sh", CONFIGURE_GUARD, TEST_GH=state)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(message, result.stderr)
                self.assertNotIn("git config --global --replace-all", calls)
                self.assertNotIn("github.com", self.git("config", "--global", "--list"))

    def check(self, **overrides):
        environment = dict(DEV_CONTAINERS_SKIP_GCOMPAT_INSTALL="true", HOMEBREW_NO_ANALYTICS="1",
                           REVIEW_INHERIT_OMP_CONFIG="1", LUNA_FACTORY_ENABLED="0", LUNA_FACTORY_CAPACITY="3")
        environment.update(overrides)
        return self.run_script("check-review-runtime.sh", CHECK_GUARD, **environment)

    def test_check_reports_ready_github_git_without_printing_credentials(self):
        result, calls = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("github.com git credentials: READY", result.stdout)
        self.assertIn("git ls-remote https://github.com/jyorko/work-jatt: READY", result.stdout)
        self.assertNotIn("gho_secret_token", result.stdout + result.stderr)
        self.assertIn("git credential fill GIT_TERMINAL_PROMPT=0", calls)
        self.assertIn("git ls-remote https://github.com/jyorko/work-jatt.git HEAD GIT_TERMINAL_PROMPT=0", calls)

    def test_check_warns_but_passes_when_git_would_prompt(self):
        result, _ = self.check(TEST_CREDENTIALS="no", TEST_REMOTE="no")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WARNING: git has no non-interactive credentials for github.com", result.stdout)
        self.assertIn("WARNING: git cannot read https://github.com/jyorko/work-jatt", result.stdout)
        self.assertIn("gh auth login", result.stdout)

    def test_check_repository_comes_from_override_or_sanitized_origin(self):
        for overrides, url in (
            ({"TEST_ORIGIN": "https://user:ghp_inline@github.com/owner/repo.git"}, "https://github.com/owner/repo.git"),
            ({"GITHUB_GIT_CHECK_REPOSITORY": "owner/private"}, "https://github.com/owner/private.git"),
        ):
            with self.subTest(overrides=overrides):
                result, calls = self.check(**overrides)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"git ls-remote {url} HEAD GIT_TERMINAL_PROMPT=0", calls)
                self.assertNotIn("ghp_inline", result.stdout + result.stderr)

    def test_check_without_a_github_origin_skips_the_read(self):
        result, calls = self.check(TEST_ORIGIN="git@gitlab.com:owner/repo.git")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("GITHUB_GIT_CHECK_REPOSITORY", result.stdout)
        self.assertFalse(any(call.startswith("git ls-remote") for call in calls))


if __name__ == "__main__":
    unittest.main()
