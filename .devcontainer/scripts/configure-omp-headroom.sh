#!/usr/bin/env bash
set -euo pipefail

: "${HEADROOM_BASE_URL:?Set HEADROOM_BASE_URL before enabling the Headroom OMP profile}"

AGENT_DIR="${HOME}/.omp/profiles/review/agent"
MODELS_FILE="${AGENT_DIR}/models.yml"

echo '==> Configuring shared Review OMP profile for Headroom'
mkdir -p "${AGENT_DIR}"

if ! command -v yq >/dev/null 2>&1; then
  echo 'ERROR: yq is required to configure the Headroom OMP profile' >&2
  exit 1
fi

temporary_file="$(mktemp "${MODELS_FILE}.tmp.XXXXXX")"
cleanup() {
  rm -f "${temporary_file}"
}
trap cleanup EXIT

if [ ! -f "${MODELS_FILE}" ]; then
  printf 'providers:\n  openai-codex:\n    baseUrl: %s\n' "${HEADROOM_BASE_URL}" > "${temporary_file}"
else
  if ! HEADROOM_BASE_URL="${HEADROOM_BASE_URL}" yq \
    '.providers."openai-codex".baseUrl = strenv(HEADROOM_BASE_URL)' \
    "${MODELS_FILE}" > "${temporary_file}"; then
    echo "ERROR: cannot parse or update Headroom OMP profile: ${MODELS_FILE}" >&2
    exit 1
  fi
fi

mv "${temporary_file}" "${MODELS_FILE}"
trap - EXIT
echo "OMP models config synchronized: ${MODELS_FILE}"
