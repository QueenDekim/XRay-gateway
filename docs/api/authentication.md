# Authentication and sessions

Sessions last 12 hours. The panel stores sessions encrypted and checks the account revision on each request. Password or role changes revoke earlier sessions.

With 2FA enabled, the first request returns a challenge without a cookie. Submit challenge and code in the second request. An unfinished login expires after three minutes.

## POST /api/login

Role: `public`.

Verify username and password. Sets the cookie on success without 2FA.

Request:

```json
{
  "username": "admin",
  "password": "example-password"
}
```

Response:

```json
{
  "requires_2fa": true,
  "challenge": "temporary-challenge"
}
```

## POST /api/login/2fa

Role: `public`.

Complete login with a TOTP or recovery code.

Request:

```json
{
  "challenge": "temporary-challenge",
  "code": "123456"
}
```

Response:

```json
{
  "ok": true
}
```

## POST /api/logout

Role: `user`.

Revoke the current session and close its RouterOS terminal.

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
