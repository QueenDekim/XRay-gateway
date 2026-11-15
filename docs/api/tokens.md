# API tokens

Open your name → API. Enter a name and a lifetime from 1 to 365 days, or select No expiry. With 2FA enabled, confirm creation, reissue and revocation with an authenticator or recovery code. Copy the full token when it appears; the panel stores its SHA-256 hash and does not display it again.

Send Authorization: Bearer <token>. A token has its owner’s permissions: regular users cannot change profiles, IP lists or RouterOS. Revocation, expiry, account deletion, password or role changes and 2FA security changes invalidate tokens.

You can keep up to 20 active tokens. Creating, listing and revoking tokens requires a panel session, plus CSRF for POST. Bearer credentials do not authorize those operations or HTML pages. On protected API routes, an invalid Authorization header returns 401 even when a valid cookie is present.

Reissue replaces the credential while preserving its name and exact expiration date, including no expiry. The old token stops working. Create a new token if the previous one has expired. Copy the replacement secret when it appears; the panel shows it once.

## GET /api/account/tokens

Role: `user (panel session)`.

Return metadata for your own tokens: id, name, prefix, created_at, expires_at and active. The response omits secrets and hashes. expires_at is null for a token with no expiry.

## POST /api/account/tokens/create

Role: `user (panel session)`.

Create a token and return 201 with the full token, item metadata and refreshed user. Require name; days defaults to 90. Set no_expiry to true to omit the expiration date; this overrides days and returns expires_at: null. no_expiry must be a boolean and defaults to false. Require code when 2FA is enabled and reject reused codes. Five failed security operations within 15 minutes trigger an escalating lockout. Allow at most 30 security requests per minute per user.

Request:

```json
{
  "name": "Monitoring",
  "days": 90,
  "code": "123456",
  "no_expiry": false
}
```

## POST /api/account/tokens/revoke

Role: `user (panel session)`.

Revoke one of your tokens by ID. Subsequent requests using it return 401. Revocation closes its RouterOS terminals. With 2FA enabled, require a fresh code. An invalid code leaves the token usable.

Request:

```json
{
  "id": "token-id",
  "code": "123456"
}
```

Response:

```json
{
  "ok": true,
  "user": {
    "id": "user-id",
    "role": "operator",
    "recovery_remaining": 8
  }
}
```

## POST /api/account/tokens/reissue

Role: `user (panel session)`.

Replace your token by ID and return 201 with token, item and user. Require a fresh code when 2FA is enabled. Keep the name and expires_at, including null; change the ID and secret. Invalidate the old token and close its RouterOS terminals.

Request:

```json
{
  "id": "token-id",
  "code": "123456"
}
```

[API index](README.md)
