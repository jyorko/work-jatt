#!/usr/bin/env sh
set -eu

SCRIPT_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
# shellcheck source=.devcontainer/josh-room.env
. "${SCRIPT_DIR}/../.devcontainer/josh-room.env"
VSIX="${JOSH_ROOM_CACHE_DIR:-${HOME}/.cache/josh-room}/josh-room-${VERSION}.vsix"
/bin/bash "${SCRIPT_DIR}/../.devcontainer/scripts/stage-josh-room.sh"

CODE_CLIS=""
if command -v code-insiders >/dev/null 2>&1; then
  CODE_CLIS="${CODE_CLIS} code-insiders"
fi
if command -v code >/dev/null 2>&1; then
  CODE_CLIS="${CODE_CLIS} code"
fi

if [ -z "${CODE_CLIS}" ]; then
  echo "VS Code CLI (code-insiders or code) was not found on PATH; run this helper after attaching to VS Code." >&2
  exit 1
fi

for CODE in ${CODE_CLIS}; do
  echo "Checking VS Code CLI: ${CODE} ($(command -v "${CODE}"))"
  if "${CODE}" --list-extensions --show-versions 2>/dev/null | grep -qx "joshyorko.josh-room@${VERSION}"; then
    echo "Josh Room ${VERSION} is already installed."
    exit 0
  fi
done

for CODE in ${CODE_CLIS}; do
  echo "Installing Josh Room ${VERSION} with ${CODE}."
  if "${CODE}" --install-extension "$VSIX" --force; then
    echo "Installed Josh Room ${VERSION} from GitHub using ${CODE}."
    exit 0
  fi
  echo "VS Code CLI ${CODE} could not install Josh Room; trying the next CLI." >&2
done

echo "Failed to install Josh Room with the available VS Code CLI(s)." >&2
exit 1
