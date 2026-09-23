#!/usr/bin/env bash
set -euo pipefail

export PATH="/home/linuxbrew/.linuxbrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"

echo '==> Installing Review runtime dependencies'
brew install -y gh apptainer squashfuse gocryptfs yq
