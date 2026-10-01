#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if /bin/bash "${SCRIPT_DIR}/check-review-runtime.sh"; then
  /bin/bash "${SCRIPT_DIR}/stage-josh-room.sh"
  echo 'Review runtime is ready.'
  exit 0
else
  check_status="$?"
fi

if [ "${check_status}" -eq 2 ]; then
  echo 'Required devcontainer environment is missing; refusing to bootstrap.' >&2
  exit "${check_status}"
fi

echo 'Review runtime is incomplete; running bootstrap.'
/bin/bash "${SCRIPT_DIR}/bootstrap-review.sh"
/bin/bash "${SCRIPT_DIR}/check-review-runtime.sh"