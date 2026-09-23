# Work Jatt

## Josh Room extension

This repository runs in a dev container. The lifecycle hooks in
[.devcontainer/devcontainer.json](.devcontainer/devcontainer.json) install the
Review tooling after the container is created, verify or repair the runtime each
time the container starts, and stage Josh Room before Devsy configures the IDE.
Devsy then installs the staged VSIX through its VS Code customization lifecycle.

The post-create hook delegates to named scripts in
[.devcontainer/scripts](.devcontainer/scripts), which install the Review
dependencies, prepare the upstream source checkout, build `fuse2fs` when it is
missing, and verify the runtime. The post-start hook runs
[.devcontainer/scripts/ensure-review-runtime.sh](.devcontainer/scripts/ensure-review-runtime.sh),
which verifies the runtime and reruns the bootstrap only when required state is
missing. The bootstrap also runs
[.devcontainer/scripts/stage-josh-room.sh](.devcontainer/scripts/stage-josh-room.sh),
which downloads the pinned Josh Room VSIX from its GitHub release, verifies its
SHA-256 checksum, and stores it at
`/home/vscode/.cache/josh-room/josh-room-0.1.24.vsix`. The
`customizations.vscode.extensions` entry points Devsy at that stable path, so
extension installation happens only after the VS Code server is available.

The bootstrap invokes each setup script through `/bin/bash`, so the lifecycle
does not depend on executable bits being preserved by the workspace checkout.
The runtime setup installs `gh`, `apptainer`, `squashfuse`, `gocryptfs`, and `yq`, and
the final check reports a clear error if a required command is still missing.
Review inherits the shared OMP configuration via `BLUEFIN_REVIEW_INHERIT_OMP_CONFIG`.

The source updater is safe to rerun: it refuses to touch a checkout with local
changes or a branch that has diverged from upstream instead of force-resetting
it. The Homebrew prefix remains part of the image rather than the persistent
`/home/vscode` volume, so a container rebuild may reinstall Homebrew packages.

Josh Room is not on the Visual Studio Marketplace, so the
extension is staged locally rather than referenced by a Marketplace ID. To
install or reinstall it manually after attaching to VS Code, run:

    sh .vscode/install-josh-room.sh

The `$schema` entry in `devcontainer.json` points to
`.vscode/devsy-devcontainer.schema.json`. The standard Dev Container schema
only accepts Marketplace extension IDs, while Devsy also accepts the staged
VSIX filesystem path used here.
