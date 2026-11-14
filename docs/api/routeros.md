# RouterOS and jobs

Configure SSH and pin the host key fingerprint. The panel stores secrets encrypted. Blank secret fields preserve existing credentials when saving the same connection.

## GET /api/routeros/config

Role: `admin`.

SSH settings without the password or private key; configured and passphrase_set describe saved credentials.

## POST /api/routeros/host-key

Role: `admin`.

Read a host fingerprint for administrator verification.

Request:

```json
{
  "host": "192.168.50.1",
  "port": 22
}
```

## POST /api/routeros/config

Role: `admin`.

Verify and save SSH access. Key authentication uses private_key and optional passphrase; password authentication uses password.

Request:

```json
{
  "host": "192.168.50.1",
  "port": 22,
  "username": "xray-panel",
  "auth": "key",
  "fingerprint": "SHA256:verified-host-key",
  "private_key": "<OpenSSH private key>",
  "passphrase": ""
}
```

## POST /api/routeros

Role: `user`.

Generate a script without executing it. Supply list_id or destinations, source, interface and local_networks.

Request:

```json
{
  "list_id": "list_0123456789ab",
  "source": "192.168.50.0/24",
  "interface": "bridge",
  "local_networks": "192.168.50.0/24"
}
```

## POST /api/routeros/apply

Role: `admin`.

Install or replace a list. Returns 202 with a job ID.

Request:

```json
{
  "id": "list_0123456789ab",
  "version": 1
}
```

Response:

```json
{
  "id": "job-id"
}
```

## GET /api/routeros/jobs

Role: `admin`.

List recent operations.

## GET /api/routeros/jobs/{id}?cursor=0

Role: `admin`.

Return status, logs and the next cursor. States: queued, running, done, error.

[API index](README.md)
