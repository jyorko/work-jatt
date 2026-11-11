#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

[[ "$(id -un)" == vscode && "$(id -u)" -ne 0 ]] || \
  fail 'Run this script inside the attached Dev Container as the non-root vscode user.'
[[ "$(cat /proc/1/comm)" == systemd ]] || \
  fail 'The devcontainer must boot the wolfi-systemd image with systemd as PID 1.'

uid="$(id -u)"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/${uid}}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"

# The pinned Wolfi image ships a root-owned /etc/shadow with mode 000.
# AppArmor's unix-chkpwd profile denies the DAC override needed to read it,
# so pam_unix fails and user@1000.service exits with 224/PAM. Mode 0600
# allows root to read the account records without granting any user access.
if [[ "$(stat -c '%u:%a' /etc/shadow)" == 0:0 ]]; then
  echo '==> Repairing root-only shadow permissions for the systemd PAM account check'
  sudo -n chmod 0600 /etc/shadow || fail 'Cannot repair /etc/shadow permissions.'
fi

# Reuse the image's startup unit to enable lingering and start the user
# manager. Starting an already active unit leaves its services running.
if ! systemctl is-active --quiet ror-vscode-user-manager.service; then
  if ! sudo -n systemctl start ror-vscode-user-manager.service; then
    systemctl status "user@${uid}.service" --no-pager >&2 || true
    fail "Cannot start the vscode user manager. Inspect: sudo journalctl -b -u user@${uid}.service"
  fi
fi
if ! systemctl is-active --quiet "user@${uid}.service"; then
  sudo -n systemctl start "user@${uid}.service" || fail 'Cannot start the vscode user manager.'
fi

systemctl is-active --quiet "user@${uid}.service" || fail 'The vscode user manager is unavailable.'
[[ -S "${XDG_RUNTIME_DIR}/bus" ]] || fail "The vscode user bus is missing at ${XDG_RUNTIME_DIR}/bus."
systemctl --user is-active --quiet default.target || fail 'Cannot reach the vscode user manager.'
busctl --user call org.freedesktop.systemd1 /org/freedesktop/systemd1 org.freedesktop.DBus.Peer Ping >/dev/null || \
  fail 'Cannot reach systemd through the vscode user bus.'
[[ "$(loginctl show-user vscode --property=Linger --value)" == yes ]] || \
  fail 'The vscode user manager needs lingering to survive SSH disconnects.'

echo 'The vscode systemd user manager and bus are ready.'
