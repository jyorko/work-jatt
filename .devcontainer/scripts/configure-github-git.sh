#!/usr/bin/env bash
set -euo pipefail

export PATH="/home/linuxbrew/.linuxbrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"

# Devsy's global credential helper only answers while its SSH agent listens, so
# git over HTTPS falls back to a prompt that T3 disables. Let gh answer for
# github.com from GH_TOKEN, GITHUB_TOKEN or its hosts file at the time git runs.
# The host-scoped entry leaves Devsy's helper in charge of every other host.
# This script never fails the caller and never reads or prints the token itself.

if ! command -v gh >/dev/null 2>&1; then
  echo 'WARNING: gh is not installed, so git over HTTPS to github.com is not configured.' >&2
  exit 0
fi
gh_path="$(command -v gh)"
expected="!${gh_path} auth git-credential"

if git config --global --get-all credential.https://github.com.helper 2>/dev/null | grep -qxF -- "${expected}"; then
  echo 'git over HTTPS to github.com already uses gh for credentials.'
  exit 0
fi

# Exit status only: the token goes to /dev/null.
if ! gh auth token --hostname github.com >/dev/null 2>&1; then
  echo 'WARNING: gh is not authenticated for github.com, so git over HTTPS to github.com is not configured.' >&2
  echo 'Next: gh auth login --hostname github.com, or rerun from a Devsy shell that has GH_TOKEN.' >&2
  exit 0
fi

echo '==> Configuring git to use gh for github.com credentials'
if ! gh auth setup-git --hostname github.com; then
  echo 'WARNING: gh auth setup-git failed; git over HTTPS to github.com may prompt for credentials.' >&2
fi
