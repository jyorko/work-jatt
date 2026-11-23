# T3 service validation

The task now installs the upstream CLI through <https://t3.codes/install.sh>
and uses its native `t3 service install` and `t3 service status` commands.
Fresh installs select the official nightly channel. Upstream documents the
[service lifecycle](https://github.com/pingdotgg/t3code/blob/main/docs/user/background-service.md).

Offline tests exercise fresh and existing installations, prerequisite failures,
installer/service failures, legacy-service refusal, telemetry persistence,
Bedrock/GitHub credential persistence, git helper setup, setup serialization, and a bounded inactive-unit failure. They run the real
setup script with stubbed download/systemd/T3 boundaries and a temporary home.
No host or existing container service is changed by these tests.

```sh
python3 -m unittest discover -s tests -p test_t3_service.py -v
bash -n .vscode/install-t3-service.sh
shellcheck .vscode/install-t3-service.sh
git diff --check
```

The historical Homebrew installation evidence does not validate this upstream
installation path. A fresh disposable `wolfi-systemd` workspace, persisted-home
recreation, SSH-disconnect behavior, and VS Code task-picker execution remain
runtime acceptance checks. Preserve the HOME volume and finish active work
before migrating a running legacy service.
