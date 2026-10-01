#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=.devcontainer/josh-room.env
source "${JOSH_ROOM_PIN_FILE:-${SCRIPT_DIR}/../josh-room.env}"
URL="https://github.com/joshyorko/josh-room/releases/download/v${VERSION}-standalone-vsix/josh-room-${VERSION}.vsix"
CACHE_DIR="${JOSH_ROOM_CACHE_DIR:-${HOME}/.cache/josh-room}"
VSIX="${CACHE_DIR}/josh-room-${VERSION}.vsix"
STABLE_VSIX="${CACHE_DIR}/josh-room.vsix"

sha256_for() {
  local file="$1"

  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${file}" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "${file}" | awk '{print $1}'
  else
    echo 'ERROR: sha256sum or shasum is required to verify Josh Room.' >&2
    return 1
  fi
}

stage_stable_vsix() {
  if [ -f "${STABLE_VSIX}" ] && [ "$(sha256_for "${STABLE_VSIX}")" = "${EXPECTED_SHA256}" ]; then
    return
  fi
  tmp="$(mktemp "${CACHE_DIR}/.josh-room-stable.XXXXXX")"
  trap 'rm -f "${tmp}"' EXIT
  cp "${VSIX}" "${tmp}"
  chmod 0644 "${tmp}"
  mv -f "${tmp}" "${STABLE_VSIX}"
  trap - EXIT
}

mkdir -p "${CACHE_DIR}"

if [ -f "${VSIX}" ] && [ "$(sha256_for "${VSIX}")" = "${EXPECTED_SHA256}" ]; then
  echo "Josh Room ${VERSION} VSIX is already staged at ${VSIX}."
  stage_stable_vsix
  exit 0
fi

command -v curl >/dev/null 2>&1 || {
  echo 'ERROR: curl is required to stage Josh Room.' >&2
  exit 1
}

tmp="$(mktemp "${CACHE_DIR}/.josh-room-${VERSION}.XXXXXX")"
cleanup() {
  rm -f "${tmp}"
}
trap cleanup EXIT

echo "==> Downloading Josh Room ${VERSION} VSIX"
curl --fail --location --silent --show-error --output "${tmp}" "${URL}"

actual_sha256="$(sha256_for "${tmp}")"
if [ "${actual_sha256}" != "${EXPECTED_SHA256}" ]; then
  echo 'ERROR: Josh Room VSIX checksum verification failed.' >&2
  echo "       expected: ${EXPECTED_SHA256}" >&2
  echo "       actual:   ${actual_sha256}" >&2
  exit 1
fi

chmod 0644 "${tmp}"
mv -f "${tmp}" "${VSIX}"
trap - EXIT

stage_stable_vsix
echo "Staged Josh Room ${VERSION} VSIX at ${VSIX}."
