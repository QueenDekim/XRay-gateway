# Panel settings

GET /api/state includes settings and their revision. Send only the fields to change and the current revision. Route settings feed RouterOS operations; saved values survive restarts.

## POST /api/settings

Role: `admin`.

Set gateway, host, source, interface, local_networks, probe_url, check_interval, fail_threshold and recover_threshold.

Request:

```json
{
  "revision": 1,
  "source": "192.168.50.0/24",
  "interface": "bridge",
  "probe_url": "https://www.gstatic.com/generate_204",
  "check_interval": 10,
  "fail_threshold": 3,
  "recover_threshold": 2
}
```

[API index](README.md)
