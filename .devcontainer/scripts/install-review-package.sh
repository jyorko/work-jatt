#!/usr/bin/env bash
set -euo pipefail

export PATH="/home/linuxbrew/.linuxbrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"

echo '==> Refreshing Homebrew formula metadata'
unset HOMEBREW_NO_AUTO_UPDATE
brew update

echo '==> Trusting Review formula'
brew trust --formula joshyorko/tools/review
# Trust this formula without validating unrelated formulae and casks in its tap.

echo '==> Installing or upgrading stable Review package'
if brew list --versions joshyorko/tools/review >/dev/null 2>&1; then
	brew upgrade joshyorko/tools/review
else
	brew install joshyorko/tools/review
fi
