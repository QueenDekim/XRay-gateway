# Operations

## Inspect and back up

```sh
docker compose ps
docker compose logs --tail=100 gateway xray
```

Back up `.env`, `secrets/` and `config/runtime/` to private storage. Runtime data
contains VLESS credentials, account hashes, saved settings and counters. Stop
both services for a consistent filesystem copy, then restart them:

```sh
docker compose stop gateway xray
tar -czf gateway-backup.tar.gz .env secrets config/runtime
docker compose start gateway xray
```

Use the extra `-f compose.proxy.yaml` option if your deployment includes it.

## Update

Read the changelog and back up first. Pull the intended release, validate the
Compose model and recreate both services together:

```sh
git pull --ff-only
docker compose config --quiet
docker compose up -d --build --force-recreate gateway xray
docker compose ps
```

The services share network and PID namespaces. Recreate both after replacing the
gateway container. Keep `XRAY_IMAGE` consistent between the application build and
the runtime core. Restore the previous code, image and runtime backup if an update
fails; avoid restoring an older database while the new services still run.

## Recover administrator access

```sh
docker compose exec gateway python3 /app/password.py
```

Enter a login and a new password. The command creates or updates that
administrator, revokes its earlier sessions and preserves other accounts. It
does not use a password supplied on the command line.

## Health checks

The health endpoint returns HTTP 200 when the Xray API responds and HTTP 503 when
it does not. Its JSON includes the selected route and profile probe results.
Restrict access to trusted monitoring systems and the router.
