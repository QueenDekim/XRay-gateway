# Updates

## Check and install

The panel checks release tags on GitHub and image manifests on GHCR every six
hours. It offers a higher semantic version after both the gateway and updater
images exist and allow anonymous pulls. A tag alone does not trigger an update.
The panel keeps the last check result if GitHub or GHCR cannot be reached.

A notification appears above the version link when a release is available.
Administrators can choose Update there or open Settings → Updates. Confirm the
version in the dialog, then follow the installation log. Read-only users see the
notification but cannot install or change update settings.

The page reconnects during the restart and reloads its current URL when it sees
the new version. Saved sessions survive restarts. A database or account security
change can still require you to sign in again.

## Automatic installation

Automatic installation starts disabled. Enable it in Settings → Updates and
choose a check interval from 1 to 168 hours. The service installs releases within
the current major version. Install a new major version after reviewing its
migration instructions. A failed unattended attempt does not retry that version
until the panel restarts; use the Update button to retry after fixing the cause.

## Installation sequence

1. Resolve the published gateway and updater images to immutable digests.
2. Download both images and the core image named by the release.
3. Block new panel writes and wait for active writes and RouterOS jobs to finish.
4. Back up runtime files, SQLite, `.env` and the previous image references.
5. Recreate gateway, Xray and updater together, preserving the LAN address, MAC
   and network aliases.
6. Check health, the displayed version and stored profile/list/account records.
7. Restore the previous images, environment and runtime backup if checks fail.

Expect a brief interruption to traffic and the panel during recreation. The
worker runs outside the managed services so their restart does not stop it.

## Docker access

Use rootful Docker Engine with the repository's Compose services named
`gateway`, `xray` and `updater`. Keep Compose files within the project directory
and runtime data on a persistent mount. The worker reads the current Compose
project labels; it supports the reverse-proxy override and custom network names.

Only `updater` mounts `/var/run/docker.sock`. The panel exchanges requests and
status through the `updates-control` volume. Requests name the two official
GHCR repositories and image digests; they cannot supply shell commands or an
arbitrary host path. The updater launches a detached worker with mounts for
this project directory, its runtime data, control volume and the Docker socket.

Docker socket access grants control of the Docker host. Run the updater only on
a trusted host and restrict administrator access to the panel. To disable panel
installation, stop and remove the updater service; manual updates still work:

```sh
docker compose stop updater
docker compose rm -f updater
```

The panel can check versions while the agent is absent, but it disables Update.
A later `docker compose up` can start the service again.

## Backup contents

Each attempt stores a private backup under `.backups/update-<job-id>/` in the
Compose project directory. `runtime.tar.gz` includes the SQLite snapshot,
account database, encrypted sessions, avatars and hidden encryption key.
`state.json` records the old image tags, Compose file list and encoded previous
`.env`; treat it as a secret. `images.override.json` and
`rollback.override.json` record the images used for installation and recovery.
A failed attempt can also create a private `debug.log`.

Keep these backups and their rollback image tags until you accept the release.
Copy backups to private off-host storage. Docker image pruning can remove the
images needed for an offline rollback.

## Recover an interrupted update

The agent detects an exited worker and starts one recovery attempt. If recovery
also fails, it leaves an error and the backup for manual repair. Inspect the
private backup on the host; panel logs omit command output that could contain
credentials.

For manual recovery, select the affected backup directory and stop the services:

```sh
backup=.backups/update-<job-id>
docker compose stop updater xray gateway
mv config/runtime config/runtime.failed
mkdir -p config/runtime
tar -xzf "$backup/runtime.tar.gz" -C config/runtime
```

Restore the old `.env` from `state.json` without printing its contents:

```sh
python3 - "$backup/state.json" <<'PY'
import base64, json, pathlib, sys
state = json.loads(pathlib.Path(sys.argv[1]).read_text())
path = pathlib.Path('.env')
if state['environment'] is None:
    path.unlink(missing_ok=True)
else:
    path.write_bytes(base64.b64decode(state['environment']))
    path.chmod(0o600)
PY
```

Use `rollback.override.json` with your original Compose files. It references the
saved local rollback images. If the worker failed before creating that file,
copy `state.json`'s `old_images` values into an override first. For the default
single-file deployment:

```sh
docker compose -f compose.yaml -f "$backup/rollback.override.json" up -d \
  --no-build --pull never --force-recreate gateway xray updater
```

With a reverse proxy, include `-f compose.proxy.yaml` before the rollback
file. Verify `/api/version`, health and routed client traffic before removing
the failed runtime copy. See [Operations](operations.md) for regular backups
and manual source/GHCR upgrades.
