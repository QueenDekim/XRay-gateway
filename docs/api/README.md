# Getting started

API paths are relative to the panel URL. Requests and responses use JSON.

Create an API token under your name → API. Send Authorization: Bearer <token> on each request. Bearer requests need no cookie or CSRF token. Use HTTPS.

Errors return an error field. Accept-Language: en selects English; Russian is the default. Status codes 400, 401, 403, 429 and 503 mean invalid input, missing session, forbidden access, rate limit and unavailable operation.

Tokens inherit their owner’s permissions. The user role accepts a regular user or administrator; admin requires an administrator. Token management requires a panel session.

## GET /api/version

Role: `public`.

Version, full source SHA and tag link. No login required.

Response:

```json
{
  "base_version": "1.9.0",
  "version": "1.9.0-abcdef0",
  "revision": "abcdef0123456789abcdef0123456789abcdef0123",
  "tag": "1.9.0-abcdef0",
  "url": "https://github.com/QueenDekim/XRay-gateway/tree/1.9.0-abcdef0"
}
```

## GET /api/state

Role: `user`.

Gateway state, profiles, lists, statistics, current user and CSRF. Only administrators receive users. Passwords and VLESS keys are omitted.

[Authentication and sessions](authentication.md) · [API tokens](tokens.md) · [Profiles and subscriptions](profiles.md) · [IP lists and domains](ip-lists.md) · [RouterOS and jobs](routeros.md) · [RouterOS terminal](terminal.md) · [Accounts and security](accounts.md) · [Panel settings](settings.md) · [Updates](updates.md)
