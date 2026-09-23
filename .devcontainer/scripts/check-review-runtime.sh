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
  LUNA_FACTORY_ENABLED \
  LUNA_FACTORY_CAPACITY; do
  require_environment "${variable_name}"
done

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
