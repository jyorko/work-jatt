#!/usr/bin/env bash
set -euo pipefail

export PATH="/home/linuxbrew/.linuxbrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"

echo '==> Installing Review runtime dependencies'
brew install -y gh apptainer squashfuse gocryptfs yq

echo '==> Installing Codex CLI'
export CODEX_NON_INTERACTIVE=1
curl -fsSL https://chatgpt.com/codex/install.sh | sh
