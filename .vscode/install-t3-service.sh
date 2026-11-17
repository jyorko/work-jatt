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

user_manager_fail() {
    systemctl status "user@${uid}.service" --no-pager >&2 || true
    fail "$* Repair the container runtime with: /bin/bash \"${script_dir}/../.devcontainer/scripts/ensure-systemd-user-manager.sh\""
}

# Succeeds when every KEY=VALUE line of the environment file is in the process's
# environment. Pure bash, so the values never appear in another command line.
service_has_environment() {
    local entry line entries=()
    local -A present=()
    [[ -r "/proc/$1/environ" ]] || return 1
    mapfile -d '' entries < "/proc/$1/environ"
    for entry in "${entries[@]}"; do
        present["${entry}"]=1
    done
    while IFS= read -r line; do
        [[ -z "${line}" || "${line}" == '#'* || -n "${present["${line}"]:-}" ]] || return 1
    done < "${environment_file}"
}

[[ "$(id -un)" == vscode && "$(id -u)" -ne 0 ]] || \
    fail 'Run this task inside the attached Dev Container as the non-root vscode user.'
[[ "${HOME}" == /home/vscode ]] || fail 'Use the vscode account HOME=/home/vscode.'
[[ "$(cat /proc/1/comm)" == systemd ]] || fail "PID 1 is not systemd. ${prerequisite}"
for command in brew systemctl busctl loginctl flock; do
    command -v "${command}" >/dev/null || fail "Missing ${command}. ${prerequisite}"
done
if command -v python3 >/dev/null; then
    python=python3
elif command -v python3.13 >/dev/null; then
    python=python3.13
else
    fail 'Missing python3 or python3.13. Install Python 3 in the devcontainer before running this task.'
fi

uid="$(id -u)"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/${uid}}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"
[[ -S "${XDG_RUNTIME_DIR}/bus" ]] || user_manager_fail "The vscode user bus is missing at ${XDG_RUNTIME_DIR}/bus."
systemctl is-active --quiet "user@${uid}.service" || user_manager_fail 'The vscode user manager is unavailable.'
systemctl --user is-active --quiet default.target || user_manager_fail 'Cannot reach the vscode user manager.'
busctl --user call org.freedesktop.systemd1 /org/freedesktop/systemd1 org.freedesktop.DBus.Peer Ping >/dev/null || \
    user_manager_fail 'Cannot reach systemd through the user bus.'
[[ "$(loginctl show-user vscode --property=Linger --value)" == yes ]] || \
    user_manager_fail 'The vscode user manager needs lingering to survive SSH disconnects.'
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
"${python}" "${script_dir}/check-t3-service.py" preflight "${service_pid:-0}"
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
"${python}" "${script_dir}/check-t3-service.py" preflight "${service_pid:-0}"

# Codex reads its Bedrock key, and T3 its GitHub token, only from the process
# environment. Devsy injects them into its SSH sessions, which systemd services
# never see, so copy them into a private file that the unit loads. A value this
# shell lacks keeps its stored copy.
config_home="${XDG_CONFIG_HOME:-${HOME}/.config}"
environment_file="${config_home}/t3code/service.env"
drop_in="${config_home}/systemd/user/${unit}.d/service-env.conf"
carried_names=(AWS_BEARER_TOKEN_BEDROCK AWS_REGION AWS_DEFAULT_REGION GH_TOKEN GITHUB_TOKEN)
declare -A carried=()
if [[ -f "${environment_file}" ]]; then
    while IFS= read -r line; do
        [[ -z "${line}" || "${line}" == '#'* ]] || carried["${line%%=*}"]="${line#*=}"
    done < "${environment_file}"
fi
for name in "${carried_names[@]}"; do
    if [[ -n "${!name:-}" ]]; then
        [[ "${!name}" =~ ^[A-Za-z0-9+/=._-]+$ ]] || \
            fail "${name} has characters a systemd environment file cannot hold."
        carried["${name}"]="${!name}"
    fi
done
if [[ -n "${carried[AWS_BEARER_TOKEN_BEDROCK]:-}" ]]; then
    : "${carried[AWS_REGION]:=${carried[AWS_DEFAULT_REGION]:-us-east-1}}"
    : "${carried[AWS_DEFAULT_REGION]:=${carried[AWS_REGION]}}"
else
    echo 'WARNING: AWS_BEARER_TOKEN_BEDROCK is not set, so Codex in T3 cannot reach Bedrock. Rerun from a Devsy shell.' >&2
fi
[[ -n "${carried[GH_TOKEN]:-}${carried[GITHUB_TOKEN]:-}" ]] || \
    echo 'WARNING: GH_TOKEN and GITHUB_TOKEN are not set, so T3 cannot reach GitHub. Rerun from a Devsy shell.' >&2
lines=''
for name in "${carried_names[@]}"; do
    [[ -z "${carried[${name}]:-}" ]] || lines+="${name}=${carried[${name}]}"$'\n'
done
if [[ -n "${lines}" ]]; then
    echo '==> Writing the Devsy credentials for the T3 service'
    mkdir -p -m 700 "${environment_file%/*}"
    staged="$(mktemp "${environment_file}.XXXXXX")"
    printf '# Written by install-t3-service.sh from the Devsy session. Rerun it after a key rotates.\n%s' \
        "${lines}" > "${staged}"
    mv -f "${staged}" "${environment_file}"
fi
drop_in_content="$(printf '[Service]\nEnvironmentFile=-%s' "${environment_file}")"
if [[ ! -f "${drop_in}" || "$(< "${drop_in}")" != "${drop_in_content}" ]]; then
    mkdir -p "${drop_in%/*}"
    printf '%s\n' "${drop_in_content}" > "${drop_in}"
    systemctl --user daemon-reload
fi
# T3 clones with git prompts disabled, so let gh answer github.com credential
# requests from the GH_TOKEN or GITHUB_TOKEN that the unit loads above. Pass the
# stored copies through the environment so a shell without them still counts.
GH_TOKEN="${carried[GH_TOKEN]:-}" GITHUB_TOKEN="${carried[GITHUB_TOKEN]:-}" \
    /bin/bash "${script_dir}/../.devcontainer/scripts/configure-github-git.sh"

echo '==> Starting the Homebrew systemd user service'
brew services start "${formula}"

verification='The service did not become active.'
deadline=$((SECONDS + 30))
while (( SECONDS < deadline )); do
    if systemctl --user is-active --quiet "${unit}"; then
        service_pid="$(systemctl --user show "${unit}" --property=MainPID --value)"
        if verification="$("${python}" "${script_dir}/check-t3-service.py" verify "${service_pid}" "${prefix}" 2>&1)"; then
            # Do not accept a listener from a process that the unit has already replaced.
            if systemctl --user is-active --quiet "${unit}" && \
                [[ "$(systemctl --user show "${unit}" --property=MainPID --value)" == "${service_pid}" ]]; then
                brew services info "${formula}"
                diagnostics
                echo "PASS: ${unit} runs as vscode. ${verification}"
                if [[ -f "${environment_file}" ]] && ! service_has_environment "${service_pid}"; then
                    echo "NOTE: The running service lacks the current Devsy credentials. Restart it to apply them; this ends running T3 agent sessions: systemctl --user restart ${unit}"
                fi
                exit 0
            fi
        fi
    fi
    sleep 1
done
diagnostics
fail "T3 was not ready within 30 seconds: ${verification}"
