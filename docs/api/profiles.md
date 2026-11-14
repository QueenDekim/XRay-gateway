# Profiles and subscriptions

Each profile has its own priority from 1 to 1000. Lower numbers win among enabled, available profiles. Configuration changes validate and restart Xray.

Preview a subscription to obtain candidates. Its selection token belongs to the session and lasts five minutes. Add accepts several profiles; replacement accepts one. Reimport updates matching records in that subscription group.

## POST /api/profiles/preview

Role: `admin`.

Download a VLESS subscription and return token, profiles, skipped and group. Candidates include ID, name, address, port, transport and security.

Request:

```json
{
  "uri": "https://example.org/subscription/token"
}
```

## POST /api/profiles/add

Role: `admin`.

Add a profile. For subscriptions, send the token, selected IDs and individual names and priorities. Read revision from /api/state.

Request:

```json
{
  "revision": 1,
  "uri": "https://example.org/subscription/token",
  "enabled": true,
  "name": "",
  "priority": 10,
  "subscription_token": "selection-token",
  "subscription_profiles": [
    "candidate-id"
  ],
  "subscription_name": "My subscription",
  "subscription_options": {
    "candidate-id": {
      "name": "Primary",
      "priority": 10
    }
  }
}
```

Response:

```json
{
  "ok": true
}
```

## POST /api/profiles/edit

Role: `admin`.

Accepts the profile ID and current revision. An empty uri preserves the connection; edit name, priority and enabled separately.

Request:

```json
{
  "id": "primary",
  "revision": 2,
  "name": "Primary",
  "priority": 5,
  "enabled": true,
  "uri": ""
}
```

Response:

```json
{
  "ok": true
}
```

## POST /api/profiles/delete

Role: `admin`.

Delete a profile by ID and revision.

Request:

```json
{
  "id": "primary",
  "revision": 2
}
```

Response:

```json
{
  "ok": true
}
```

## POST /api/profiles/reset-checks

Role: `admin`.

Reset total and successful probe counts. Keep traffic counters.

Request:

```json
{}
```

Response:

```json
{
  "ok": true
}
```

[API index](README.md)
