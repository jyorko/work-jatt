#!/usr/bin/env bash
set -euo pipefail

export PATH="/home/linuxbrew/.linuxbrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"
# Homebrew now prompts before installing multiple dependencies; force non-interactive.
export NONINTERACTIVE=1
export HOMEBREW_NO_AUTO_UPDATE=1

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

run_script() {
	local script_name="$1"

	echo "==> Running ${script_name}"
	/bin/bash "${SCRIPT_DIR}/${script_name}"
}

# Invoke child scripts through Bash instead of relying on executable bits. This
# also works when the workspace was checked out with scripts tracked as 0644.
run_script install-review-tools.sh
run_script install-review-package.sh
run_script prepare-review-source.sh
run_script build-fuse2fs.sh
run_script stage-josh-room.sh

run_script check-review-runtime.sh
