# Work Jatt

## Start the T3 service

The devcontainer uses the tested `wolfi-systemd` image. T3 starts only through
the manual VS Code task, not during container bootstrap.

Inside the attached container, choose **Tasks: Run Task → T3: Install and start
service**. The task installs `joshyorko/tools/t3code-cli-main` only when missing
and starts its Homebrew systemd user service as `vscode`. It verifies the
service's process and owned TCP listener before reporting success. Repeated runs
keep the installed formula version and a healthy service running.
The task uses `python3`, or the image's `python3.13` when `python3` is not
on its PATH; activating a workspace virtual environment is not required.

Check or manage the service inside the container as `vscode`:

```sh
systemctl --user status sh.brew.t3code-cli-main.service
brew services stop t3code-cli-main
brew services restart t3code-cli-main
```

The task reports competing T3 servers or listeners without stopping them. After
recreating the container, rerun the task to reinstall the formula if needed.

## Josh Room extension

This repository runs in a dev container. The lifecycle hooks in
[.devcontainer/devcontainer.json](.devcontainer/devcontainer.json) install the
Review tooling after the container is created, verify or repair the runtime each
time the container starts, and stage Josh Room before Devsy configures the IDE.
Devsy then installs the staged VSIX through its VS Code customization lifecycle.

The devcontainer uses the published Wolfi image directly, matching the working
personal setup and avoiding a Dockerless build on Kubernetes.

The post-create hook delegates to named scripts in
[.devcontainer/scripts](.devcontainer/scripts), which install the Review
dependencies and the stable Homebrew Review package, build `fuse2fs` when it is
missing, and verify the runtime. The post-start hook runs
[.devcontainer/scripts/ensure-review-runtime.sh](.devcontainer/scripts/ensure-review-runtime.sh),
which verifies the runtime and reruns the bootstrap only when required state is
missing. The bootstrap also runs
[.devcontainer/scripts/stage-josh-room.sh](.devcontainer/scripts/stage-josh-room.sh),
which downloads the pinned Josh Room VSIX from its GitHub release, verifies its
SHA-256 checksum, and stores it at
`/home/vscode/.cache/josh-room/josh-room.vsix`. The
`customizations.vscode.extensions` entry points Devsy at that stable path, so
extension installation happens only after the VS Code server is available.

Each container start also updates `~/.codex/config.toml` to use GPT-5.6 Luna
through Amazon Bedrock in `us-east-1`, with the configured reasoning and
context limits. Other Codex settings are retained.

The version and SHA-256 checksum live in
[.devcontainer/josh-room.env](.devcontainer/josh-room.env). To update to the
latest published release, run from the repository root on the host or inside
the devcontainer:

    bash .vscode/update-josh-room.sh

The updater finds the latest release on GitHub, reads its `SHA256SUMS`, downloads
and verifies the VSIX, and only then changes the pin. To pin a specific release,
pass its version and, optionally, a known SHA-256 checksum.

The devcontainer extension path stays the same across releases.
Staging uses the current user's `~/.cache/josh-room`; set
`JOSH_ROOM_CACHE_DIR` to override it.

The bootstrap invokes each setup script through `/bin/bash`, so the lifecycle
does not depend on executable bits being preserved by the workspace checkout.
The runtime setup installs `gh`, `apptainer`, `squashfuse`, `gocryptfs`, and `yq` via
Homebrew, and the Codex CLI via its official installer
(`curl -fsSL https://chatgpt.com/codex/install.sh | sh`, which stages the binary at
`~/.local/bin/codex`). The final check reports a clear error if a required
command is still missing.
Review is installed or upgraded from `joshyorko/tools/review`. Run
`review owner/repo` with an explicit GitHub repository scope. Review inherits
the shared OMP configuration via `REVIEW_INHERIT_OMP_CONFIG`.

Bootstrap no longer creates or updates `~/src/review`; existing checkouts and
user data are left untouched. The Homebrew prefix remains part of the image
rather than the persistent
`/home/vscode` volume, so a container rebuild may reinstall Homebrew packages.

Josh Room is not on the Visual Studio Marketplace, so the
extension is staged locally rather than referenced by a Marketplace ID. To
install or reinstall it manually after attaching to VS Code, run:

    sh .vscode/install-josh-room.sh

Run the install command inside the attached devcontainer to update its
extension, or on the host to update the host's VS Code installation. Reload
the VS Code window after installation to load the new version.

The `$schema` entry in `devcontainer.json` points to
`.vscode/devsy-devcontainer.schema.json`. The standard Dev Container schema
only accepts Marketplace extension IDs, while Devsy also accepts the staged
VSIX filesystem path used here.
