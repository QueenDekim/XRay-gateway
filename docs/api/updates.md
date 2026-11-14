# Updates

Checks select a newer version with published Gateway and Updater images. Installation pins image digests, backs up data, recreates the Compose services and rolls back if verification fails.

Automatic installation is off by default; periodic checks are on. Configure the updater service, which alone receives the Docker socket. Write operations return 503 during installation.

## GET /api/updates

Role: `user`.

Current and available versions, check time, updater availability and job status. Settings and detailed logs require an administrator.

## POST /api/updates/check

Role: `admin`.

Start a background check and return 202. Checks are limited to once per minute.

Request:

```json
{}
```

## POST /api/updates/settings

Role: `admin`.

Check interval: 1 to 168 hours. auto_install controls automatic installation.

Request:

```json
{
  "check_interval_hours": 6,
  "auto_install": false
}
```

## POST /api/updates/install

Role: `admin`.

Install the available tag returned by a check. Returns 202 with the job ID; read /api/updates for progress.

Request:

```json
{
  "tag": "1.9.0-abcdef0"
}
```

Response:

```json
{
  "id": "update-job-id"
}
```

[API index](README.md)
