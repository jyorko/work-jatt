#!/usr/bin/env bash
set -euo pipefail

export PATH="/home/linuxbrew/.linuxbrew/bin:/home/linuxbrew/.linuxbrew/sbin:${PATH}"
export HOMEBREW_NO_ANALYTICS=1
export HOMEBREW_NO_AUTO_UPDATE=1
formula=joshyorko/tools/t3code-cli-main
unit=sh.brew.t3code-cli-main.service
script_dir="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)"
prerequisite='Use the wolfi-systemd devcontainer from https://github.com/joshyorko/work-jatt/issues/5.'

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

diagnostics() {
    systemctl --user show "${unit}" --no-pager \
        --property=ActiveState,SubState,Result,MainPID,ExecMainStatus,NRestarts >&2 || true
}

[[ "$(id -un)" == vscode && "$(id -u)" -ne 0 ]] || \
    fail 'Run this task inside the attached Dev Container as the non-root vscode user.'
[[ "${HOME}" == /home/vscode ]] || fail 'Use the vscode account HOME=/home/vscode.'
[[ "$(cat /proc/1/comm)" == systemd ]] || fail "PID 1 is not systemd. ${prerequisite}"
for command in brew systemctl busctl loginctl flock; do
    command -v "${command}" >/dev/null || fail "Missing ${command}. ${prerequisite}"
done
command -v python3 >/dev/null || fail 'Missing python3. Complete the Work-Jatt devcontainer bootstrap before running this task.'

uid="$(id -u)"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/${uid}}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"
[[ -S "${XDG_RUNTIME_DIR}/bus" ]] || fail "The vscode user bus is missing. ${prerequisite}"
systemctl is-active --quiet "user@${uid}.service" || fail "The vscode user manager is unavailable. ${prerequisite}"
systemctl --user is-active --quiet default.target || fail "Cannot reach the vscode user manager. ${prerequisite}"
busctl --user call org.freedesktop.systemd1 /org/freedesktop/systemd1 org.freedesktop.DBus.Peer Ping >/dev/null || \
    fail "Cannot reach systemd through the user bus. ${prerequisite}"
[[ "$(loginctl show-user vscode --property=Linger --value)" == yes ]] || \
    fail "The vscode user manager needs lingering to survive SSH disconnects. ${prerequisite}"
manager_state="$(systemctl is-system-running || true)"
case "${manager_state}" in
    running) ;;
    degraded)
        echo 'WARNING: The system manager is degraded; required user manager and bus are available.' >&2
        systemctl --failed --no-pager --plain >&2 || true
        ;;
    *) fail "The system manager is ${manager_state:-unavailable}. ${prerequisite}" ;;
esac

exec 9>"${XDG_RUNTIME_DIR}/work-jatt-t3-service.lock"
flock -n 9 || fail 'Another T3 service setup is running. Wait for it to finish.'
trap 'diagnostics' ERR

service_pid="$(systemctl --user show "${unit}" --property=MainPID --value 2>/dev/null || true)"
python3 "${script_dir}/check-t3-service.py" preflight "${service_pid:-0}"
if ! brew list --versions "${formula}" >/dev/null 2>&1; then
    echo '==> Installing the Homebrew T3 formula'
    # Trusting the qualified formula also taps it, without validating unrelated casks.
    brew trust --formula "${formula}"
    brew install --formula "${formula}"
else
    echo '==> Keeping the installed T3 formula version'
fi
prefix="$(brew --prefix "${formula}")"

# Check again after installation in case another terminal started a server.
service_pid="$(systemctl --user show "${unit}" --property=MainPID --value 2>/dev/null || true)"
python3 "${script_dir}/check-t3-service.py" preflight "${service_pid:-0}"
echo '==> Starting the Homebrew systemd user service'
brew services start "${formula}"

verification='The service did not become active.'
deadline=$((SECONDS + 30))
while (( SECONDS < deadline )); do
    if systemctl --user is-active --quiet "${unit}"; then
        service_pid="$(systemctl --user show "${unit}" --property=MainPID --value)"
        if verification="$(python3 "${script_dir}/check-t3-service.py" verify "${service_pid}" "${prefix}" 2>&1)"; then
            # Do not accept a listener from a process that the unit has already replaced.
            if systemctl --user is-active --quiet "${unit}" && \
                [[ "$(systemctl --user show "${unit}" --property=MainPID --value)" == "${service_pid}" ]]; then
                brew services info "${formula}"
                diagnostics
                echo "PASS: ${unit} runs as vscode. ${verification}"
                exit 0
            fi
        fi
    fi
    sleep 1
done
diagnostics
fail "T3 was not ready within 30 seconds: ${verification}"
