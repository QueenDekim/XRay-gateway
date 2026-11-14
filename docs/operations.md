# Operations

## Inspect and back up

```sh
docker compose ps
docker compose logs --tail=100 gateway xray updater
```

Back up `.env`, `secrets/` and `config/runtime/` to private storage. Runtime data
contains VLESS credentials, account hashes, saved settings and counters. Stop
the three services for a consistent filesystem copy, then restart them:

```sh
docker compose stop gateway xray updater
umask 077
tar -czf gateway-backup.tar.gz .env secrets config/runtime compose*.yaml
docker compose start gateway xray updater
```

Use the extra `-f compose.proxy.yaml` option if your deployment includes it.

Include hidden files. `config/runtime/.encryption-key` decrypts saved RouterOS
credentials and 2FA secrets; restore it together with `routeros.json` and
`auth.json`. Keep this backup private. Avatars live in `config/runtime/avatars/`.

## Manual update

For panel-managed installation, see [Updates](updates.md). To update from a
shell, back up first and read the changelog. Preserve your `.env`, Compose
network configuration and runtime directory when updating the checkout.

For a source build:

```sh
git pull --ff-only
docker compose config --quiet
docker compose build gateway updater
docker compose stop xray gateway updater
docker compose up -d --no-build --force-recreate gateway xray updater
docker compose ps
```

For GHCR images, set `GATEWAY_IMAGE` and `UPDATER_IMAGE` in `.env` to the same
release, and set `XRAY_IMAGE` to that release's pinned core. Pull before stopping
the running services:

```sh
docker compose config --quiet
docker compose pull gateway xray updater
docker compose stop xray gateway updater
docker compose up -d --no-build --force-recreate gateway xray updater
docker compose ps
```

The gateway and core share network and PID namespaces. Recreate them together.
Check `/api/version`, the health endpoint and client traffic through your
RouterOS policy after the update.

## Manual restore

Stop the updater before restoring data so it cannot start another installation.
Use the same Compose file list as your deployment. Preserve the failed state
before extracting a private backup in the project directory:

```sh
docker compose stop updater xray gateway
mv config/runtime config/runtime.failed
tar -xzf gateway-backup.tar.gz
```

Restore the previous source revision and rebuild, or pin `.env` to the previous
gateway and updater images and matching core. Then run:

```sh
docker compose config --quiet
docker compose up -d --no-build --force-recreate gateway xray updater
docker compose ps
```

Use the worker's [recovery instructions](updates.md#recover-an-interrupted-update)
for a backup under `.backups/update-<job-id>`; its archive has a different layout.

## Recover administrator access

```sh
docker compose exec gateway python3 /app/password.py
```

Enter a login and a new password. The command creates or updates that
administrator, revokes its earlier sessions and preserves other accounts. It
does not use a password supplied on the command line.

For an account with 2FA, answer the additional prompt to disable it if you lost
the authenticator and recovery codes. The command preserves 2FA unless you
confirm that prompt. Re-enroll the account after regaining access.

## Health checks

The health endpoint returns HTTP 200 when the Xray API responds and HTTP 503 when
it does not. Its JSON includes the selected route and profile probe results.
Restrict access to trusted monitoring systems and the router.
