#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -gt 2 ]; then
  echo 'Usage: bash .vscode/update-josh-room.sh [VERSION [SHA256]]' >&2
  exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ "$#" -eq 0 ]; then
  RELEASE_JSON="$(curl --fail --location --silent --show-error \
    https://api.github.com/repos/joshyorko/josh-room/releases/latest)"
  RELEASE_TAG="$(sed -nE 's/^[[:space:]]*"tag_name":[[:space:]]*"([^"]+)".*/\1/p' <<< "${RELEASE_JSON}")"
  if [[ ! "${RELEASE_TAG}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+-standalone-vsix$ ]]; then
    echo 'ERROR: could not find a latest Josh Room release with a supported standalone VSIX tag.' >&2
    exit 1
  fi
  VERSION="${RELEASE_TAG#v}"
  VERSION="${VERSION%-standalone-vsix}"
else
  VERSION="${1#v}"
  VERSION="${VERSION%-standalone-vsix}"
fi

if [[ ! "${VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo 'ERROR: expected a version such as 0.1.26 or v0.1.26-standalone-vsix.' >&2
  exit 1
fi

PIN_FILE="${SCRIPT_DIR}/../.devcontainer/josh-room.env"
if [ "$#" -eq 2 ]; then
  EXPECTED_SHA256="$2"
else
  RELEASE_URL="https://github.com/joshyorko/josh-room/releases/download/v${VERSION}-standalone-vsix"
  CHECKSUMS="$(curl --fail --location --silent --show-error "${RELEASE_URL}/SHA256SUMS")"
  EXPECTED_SHA256="$(awk -v asset="josh-room-${VERSION}.vsix" '$2 == asset { print $1 }' <<< "${CHECKSUMS}")"
fi
if [[ ! "${EXPECTED_SHA256}" =~ ^[0-9a-f]{64}$ ]]; then
  echo 'ERROR: expected one SHA-256 checksum for the release VSIX.' >&2
  exit 1
fi

tmp="$(mktemp "${PIN_FILE}.XXXXXX")"
trap 'rm -f "${tmp}"' EXIT
printf 'VERSION="%s"\nEXPECTED_SHA256="%s"\n' "${VERSION}" "${EXPECTED_SHA256}" > "${tmp}"
JOSH_ROOM_PIN_FILE="${tmp}" /bin/bash "${SCRIPT_DIR}/../.devcontainer/scripts/stage-josh-room.sh"
chmod 0644 "${tmp}"
mv -f "${tmp}" "${PIN_FILE}"
trap - EXIT

echo "Pinned Josh Room ${VERSION}."
echo 'To install it in the current VS Code environment, run: sh .vscode/install-josh-room.sh'
