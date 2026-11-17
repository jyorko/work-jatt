#!/usr/bin/env bash
set -euo pipefail

export PATH="${HOME}/.local/bin:/home/linuxbrew/.linuxbrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

require_environment() {
  local variable_name="$1"

  if [ -n "${!variable_name:-}" ]; then
    printf '%-36s %s\n' "${variable_name}:" "${!variable_name}"
  else
    echo "ERROR: required devcontainer environment variable is missing: ${variable_name}" >&2
    return 2
  fi
}

# Git as T3 runs it: no terminal or askpass prompt, and bounded on a stalled
# network. Callers discard its output so no credential is printed.
non_interactive_git() {
  GIT_TERMINAL_PROMPT=0 GIT_ASKPASS='' SSH_ASKPASS='' timeout 30 git "$@"
}

# Reports, without failing the check, whether git can authenticate to
# github.com and read a repository without prompting.
check_github_git() {
  local repository="${GITHUB_GIT_CHECK_REPOSITORY:-}" origin

  if printf 'protocol=https\nhost=github.com\n\n' | non_interactive_git credential fill 2>/dev/null | \
    grep '^password=' >/dev/null; then
    echo 'github.com git credentials: READY'
  else
    echo 'WARNING: git has no non-interactive credentials for github.com.'
    echo '         Next: gh auth login, then bash .devcontainer/scripts/configure-github-git.sh'
  fi

  if [ -z "${repository}" ]; then
    origin="$(git -C "${SCRIPT_DIR}" remote get-url origin 2>/dev/null || true)"
    if [[ "${origin}" =~ ^https://([^/@]*@)?github\.com/([^/]+/[^/]+)$ ]]; then
      repository="${BASH_REMATCH[2]%.git}"
    fi
  fi
  if [ -z "${repository}" ]; then
    echo 'NOTE: set GITHUB_GIT_CHECK_REPOSITORY=owner/repo to check reading a github.com repository.'
  elif non_interactive_git ls-remote "https://github.com/${repository}.git" HEAD >/dev/null 2>&1; then
    echo "git ls-remote https://github.com/${repository}: READY"
  else
    echo "WARNING: git cannot read https://github.com/${repository} without prompting."
  fi
}

require_command() {
  local command_name="$1"

  if command -v "${command_name}" >/dev/null 2>&1; then
    printf '%-12s %s\n' "${command_name}:" "$(command -v "${command_name}")"
  else
    echo "ERROR: required Review runtime command is missing: ${command_name}" >&2
    return 1
  fi
}

printf '\n=== Dev container environment ===\n'
for variable_name in \
  DEV_CONTAINERS_SKIP_GCOMPAT_INSTALL \
  HOMEBREW_NO_ANALYTICS \
  REVIEW_INHERIT_OMP_CONFIG \
  LUNA_FACTORY_ENABLED \
  LUNA_FACTORY_CAPACITY; do
  require_environment "${variable_name}"
done

printf '\n=== Installed Review package ===\n'
brew list --versions joshyorko/tools/review
printf '\n=== Review runtime ===\n'
require_command gh
require_command apptainer
require_command squashfuse
require_command gocryptfs
require_command fuse2fs
require_command review
require_command yq
require_command codex
printf '\n'
if [ -e /dev/fuse ]; then
  echo '/dev/fuse: READY'
else
  echo 'WARNING: /dev/fuse is missing'
fi
if [ -e /dev/kvm ]; then
  echo '/dev/kvm: READY'
else
  echo 'WARNING: /dev/kvm is missing'
fi
printf '\n=== GitHub over HTTPS ===\n'
check_github_git
printf '\nReview runtime check complete.\n'
echo 'Next: gh auth login'
echo 'Run: review owner/repo'
