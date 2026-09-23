#!/usr/bin/env bash
set -euo pipefail

export PATH="/home/linuxbrew/.linuxbrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH}"

require_environment() {
  local variable_name="$1"

  if [ -n "${!variable_name:-}" ]; then
    printf '%-36s %s\n' "${variable_name}:" "${!variable_name}"
  else
    echo "ERROR: required devcontainer environment variable is missing: ${variable_name}" >&2
    return 2
  fi
}

require_command() {
  local command_name="$1"

  if command -v "${command_name}" >/dev/null 2>&1; then
    printf '%-12s %s\n' "${command_name}:" "$(command -v "${command_name}")"
  else
    echo "ERROR: required Review runtime command is missing: ${command_name}" >&2
    return 1
  fi
}

printf '\n=== Dev container environment ===\n'
for variable_name in \
  DEV_CONTAINERS_SKIP_GCOMPAT_INSTALL \
  HOMEBREW_NO_ANALYTICS \
  REVIEW_UPSTREAM_REF \
  BLUEFIN_REVIEW_INHERIT_OMP_CONFIG \
  HEADROOM_BASE_URL \
  LUNA_FACTORY_ENABLED \
  LUNA_FACTORY_CAPACITY; do
  require_environment "${variable_name}"
done

require_headroom_profile() {
  local models_file="${HOME}/.omp/profiles/review/agent/models.yml"

  if [ ! -f "${models_file}" ]; then
    echo "ERROR: Headroom OMP profile is missing: ${models_file}" >&2
    return 1
  fi

  if HEADROOM_BASE_URL="${HEADROOM_BASE_URL}" yq -e \
    '.providers."openai-codex".baseUrl == strenv(HEADROOM_BASE_URL)' \
    "${models_file}" >/dev/null; then
    printf '%-36s %s\n' 'Headroom OMP profile:' "${models_file}"
  else
    echo "ERROR: Headroom OMP profile does not match HEADROOM_BASE_URL: ${models_file}" >&2
    return 1
  fi
}

printf '\n=== Review source ===\n'
git -C "${HOME}/src/review" log -1 --oneline
printf '\n=== Installed Review package ===\n'
brew list --versions joshyorko/review-dev/bluefin-review-dev
printf '\n=== Review runtime ===\n'
require_command gh
require_command apptainer
require_command squashfuse
require_command gocryptfs
require_command fuse2fs
require_command bluefin
require_command yq
require_headroom_profile
printf '\n'
if [ -e /dev/fuse ]; then
  echo '/dev/fuse: READY'
else
  echo 'WARNING: /dev/fuse is missing'
fi
if [ -e /dev/kvm ]; then
  echo '/dev/kvm: READY'
else
  echo 'WARNING: /dev/kvm is missing'
fi
printf '\nReview runtime check complete.\n'
echo 'Next: gh auth login'
echo 'Review source: ~/src/review (upstream/main)'
echo 'Run: bluefin review projectbluefin/review'
